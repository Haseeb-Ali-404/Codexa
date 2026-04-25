import logging
import subprocess
import textwrap
import zlib
from pathlib import Path

import requests
from PIL import Image, ImageDraw, ImageFont

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DEFAULT_PLANTUML_SERVER = "https://www.plantuml.com/plantuml/png"
LOCAL_PLANTUML_JAR = Path(__file__).parent.parent.parent / "bin" / "plantuml-java8-SNAPSHOT.jar"

_PLANTUML_STYLE = "\n".join(
    [
        "skinparam monochrome true",
        "skinparam shadowing false",
        "skinparam dpi 160",
        "skinparam handwritten false",
        "skinparam packageStyle rectangle",
        "skinparam defaultFontName sans-serif",
        "skinparam ArrowColor #1e293b",
    ]
)


def _encode6bit(value: int) -> str:
    if value < 10:
        return chr(48 + value)
    value -= 10
    if value < 26:
        return chr(65 + value)
    value -= 26
    if value < 26:
        return chr(97 + value)
    value -= 26
    if value == 0:
        return "-"
    if value == 1:
        return "_"
    return "?"


def _append3bytes(b1: int, b2: int, b3: int) -> str:
    c1 = b1 >> 2
    c2 = ((b1 & 0x3) << 4) | (b2 >> 4)
    c3 = ((b2 & 0xF) << 2) | (b3 >> 6)
    c4 = b3 & 0x3F
    return "".join(_encode6bit(value) for value in (c1, c2, c3, c4))


def encode_plantuml_text(text: str) -> str:
    compressor = zlib.compressobj(level=9, wbits=-15)
    compressed = compressor.compress(text.encode("utf-8")) + compressor.flush()

    encoded_parts: list[str] = []
    for i in range(0, len(compressed), 3):
        chunk = compressed[i : i + 3]
        if len(chunk) == 3:
            encoded_parts.append(_append3bytes(chunk[0], chunk[1], chunk[2]))
        elif len(chunk) == 2:
            encoded_parts.append(_append3bytes(chunk[0], chunk[1], 0))
        else:
            encoded_parts.append(_append3bytes(chunk[0], 0, 0))
    return "".join(encoded_parts)


def ensure_wrapped_plantuml(code: str, diagram_type: str | None = None) -> str:
    body = (code or "").strip()
    if not body:
        label = (diagram_type or "diagram").replace("_", " ").title()
        body = f"title {label}\n\nNo diagram content provided."

    body_without_skinparams = "\n".join(
        [line for line in body.splitlines() if not line.strip().startswith("skinparam")]
    )

    if "@startuml" not in body_without_skinparams:
        body_without_skinparams = f"@startuml\n{body_without_skinparams}\n@enduml"

    final_body = body_without_skinparams.replace("@startuml", f"@startuml\n{_PLANTUML_STYLE}", 1)

    return final_body


def render_plantuml_png(
    code: str, server_url: str | None = None, timeout: int = 30, local_jar: Path | None = None
) -> bytes:
    final_code = ensure_wrapped_plantuml(code)

    # Try local rendering first if a JAR path is provided and exists
    if local_jar and local_jar.exists():
        try:
            logger.info(f"Attempting to render PlantUML locally using {local_jar}")
            command = ["java", "-Djava.awt.headless=true", "-jar", str(local_jar), "-pipe"]
            result = subprocess.run(
                command,
                input=final_code.encode("utf-8"),
                capture_output=True,
                check=True,
                timeout=timeout,
            )
            if result.stdout:
                logger.info("Local PlantUML rendering successful.")
                return result.stdout
            raise ValueError("Local PlantUML process ran but produced no output.")
        except FileNotFoundError:
            logger.error("`java` command not found. Please ensure Java is installed and in your PATH.")
        except subprocess.CalledProcessError as e:
            logger.warning(
                f"Local PlantUML rendering failed with return code {e.returncode}. "
                f"Stderr: {e.stderr.decode('utf-8', 'ignore')}"
            )
        except subprocess.TimeoutExpired:
            logger.warning(f"Local PlantUML rendering timed out after {timeout} seconds.")
        except Exception as e:
            logger.warning(f"An unexpected error occurred during local PlantUML rendering: {e}")

    # Fallback to remote server
    logger.info("Falling back to remote PlantUML server")
    encoded = encode_plantuml_text(final_code)
    base_url = (server_url or DEFAULT_PLANTUML_SERVER).rstrip("/")
    response = requests.get(f"{base_url}/{encoded}", timeout=timeout)
    response.raise_for_status()
    return response.content


def _load_font(size: int, bold: bool = False):
    candidates = [
        "C:/Windows/Fonts/consola.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
    ]
    for candidate in candidates:
        try:
            return ImageFont.truetype(candidate, size)
        except Exception:
            pass
    return ImageFont.load_default()


def _render_fallback_diagram_image(code: str, output_path: Path, title: str | None = None) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", (1600, 1200), (249, 250, 251))
    draw = ImageDraw.Draw(image)

    draw.rectangle((0, 0, 1600, 120), fill=(15, 23, 42))
    draw.text((80, 40), title or "UML Diagram", fill=(248, 250, 252), font=_load_font(42, bold=True))
    draw.text(
        (80, 150),
        "PlantUML rendering failed. A textual fallback image was generated.",
        fill=(51, 65, 85),
        font=_load_font(24),
    )

    wrapped = textwrap.fill(ensure_wrapped_plantuml(code), width=110)
    draw.multiline_text((80, 220), wrapped, fill=(15, 23, 42), font=_load_font(20), spacing=10)
    image.save(output_path, format="PNG")


def render_plantuml_png_file(
    code: str,
    output_path: str | Path,
    *,
    server_url: str | None = None,
    timeout: int = 30,
    title: str | None = None,
) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        image_data = render_plantuml_png(code, server_url=server_url, timeout=timeout, local_jar=LOCAL_PLANTUML_JAR)
        path.write_bytes(image_data)
        logger.info(f"Successfully rendered PlantUML diagram to {path}")
    except Exception as e:
        logger.error(f"All rendering methods failed for PlantUML: {e}")
        _render_fallback_diagram_image(code, path, title=title)
    return path