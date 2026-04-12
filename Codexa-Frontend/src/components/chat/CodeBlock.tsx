import { useState } from "react";
import { cn } from "@/lib/utils";
import { Copy, Check, Terminal } from "lucide-react";

interface CodeBlockProps {
  code: string;
  language?: string;
  onCodeGenerated?: (
    code: string,
    lang: string,
    html: string,
    new_project_id: string,
  ) => void;
}

export function CodeBlock({ code, language = "typescript", }: CodeBlockProps) {
  const [copied, setCopied] = useState(false);
  const handleCopy = async () => {
    await navigator.clipboard.writeText(code);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };
  return (
    <div className="rounded-xl overflow-auto bg-card/80 border max-h-[800px] border-border/50 my-3 animate-fade-in-scale">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-2 bg-secondary/50 border-b border-border/50">
        <div className="flex items-center gap-2">
          <Terminal className="w-4 h-4 text-primary" />
          <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
            {/* {language} */}
          </span>
        </div>
        {/* <button
          onClick={handleCopy}
          className={cn(
            "flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-medium transition-all duration-200",
            copied
              ? "bg-emerald-500/20 text-emerald-400"
              : "hover:bg-secondary text-muted-foreground hover:text-foreground",
          )}
        >
          {copied ? (
            <>
              <Check className="w-3.5 h-3.5" />
              <span>Copied!</span>
            </>
          ) : (
            <>
              <Copy className="w-3.5 h-3.5" />
              <span>Copy</span>
            </>
          )}
        </button> */}
      </div>

      {/* Code Content */}
      <div className="p-4 overflow-x-auto scrollbar-thin">
        <pre className="text-sm font-mono text-foreground/90 leading-relaxed">
          <code>{code}</code>
          
        </pre>
      </div>
    </div>
  );
}
