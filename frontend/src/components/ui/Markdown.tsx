import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { cn } from "./index";

export function Markdown({ children, className }: { children: string; className?: string }) {
  return <div className={cn("prose-hl text-sm", className)}><ReactMarkdown remarkPlugins={[remarkGfm]}>{children}</ReactMarkdown></div>;
}
