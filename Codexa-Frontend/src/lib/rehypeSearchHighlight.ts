import { visit } from "unist-util-visit";

type HastText = { type: "text"; value: string };
type HastElement = {
  type: "element";
  tagName: string;
  properties?: { className?: string | string[] | number | boolean | null };
  children: HastNode[];
};
type HastRoot = { type: "root"; children: HastNode[] };
type HastNode = HastText | HastElement | { type: string; children?: HastNode[] };

export function escapeRegExp(s: string) {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function isLanguageCodeBlock(el: HastElement): boolean {
  if (el.tagName !== "code") return false;
  const cls = el.properties?.className;
  const list = Array.isArray(cls)
    ? cls.map(String)
    : cls != null
      ? [String(cls)]
      : [];
  return list.some((c) => c.startsWith("language-"));
}

export type SearchHighlightVariant = "default" | "user";

export function rehypeSearchHighlight(options: {
  query: string;
  variant: SearchHighlightVariant;
}) {
  const q = options.query.trim();
  const variant = options.variant;

  return (tree: HastRoot) => {
    if (!q) return;

    visit(tree, "text", (node: HastText, index, parent) => {
      if (index === undefined || !parent || parent.type !== "element") return;
      const el = parent as HastElement;
      if (el.tagName === "mark") return;
      if (el.tagName === "code" && isLanguageCodeBlock(el)) return;

      const value = node.value;
      if (!value) return;

      const re = new RegExp(escapeRegExp(q), "gi");
      const segments: HastNode[] = [];
      let last = 0;
      let m: RegExpExecArray | null;
      while ((m = re.exec(value)) !== null) {
        if (m.index > last) {
          segments.push({ type: "text", value: value.slice(last, m.index) });
        }
        const cls =
          variant === "user"
            ? ["chat-search-mark", "chat-search-mark-user"]
            : ["chat-search-mark"];
        segments.push({
          type: "element",
          tagName: "mark",
          properties: { className: cls },
          children: [{ type: "text", value: m[0] }],
        });
        last = m.index + m[0].length;
      }
      if (last < value.length) {
        segments.push({ type: "text", value: value.slice(last) });
      }
      if (segments.length <= 1) return;

      el.children.splice(index, 1, ...segments);
    });
  };
}
