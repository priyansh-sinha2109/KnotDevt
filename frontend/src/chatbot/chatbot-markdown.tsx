"use client";

/**
 * Safe markdown renderer for chatbot messages.
 *
 * This does NOT use dangerouslySetInnerHTML. All text is rendered through JSX,
 * which automatically escapes content. Only a subset of markdown is supported:
 * headers, bold, italic, inline code, internal links, and lists.
 *
 * External URLs and raw HTML are never rendered as links — they appear as
 * plain text. Only paths starting with "/" (internal KnotDevt navigation) are
 * rendered as clickable links.
 */

import { type ReactNode } from "react";

interface Token {
  type: "text" | "bold" | "italic" | "code" | "link" | "linebreak";
  content: string;
  href?: string;
}

function parseInline(text: string): Token[] {
  const tokens: Token[] = [];
  // Regex for: bold (**...**), italic (*...*), code (`...`), link ([text](url))
  const pattern =
    /\*\*(.+?)\*\*|\*(.+?)\*|`(.+?)`|\[(.+?)\]\(([^)]+)\)/g;
  let lastIndex = 0;
  let match: RegExpExecArray | null;

  while ((match = pattern.exec(text)) !== null) {
    if (match.index > lastIndex) {
      tokens.push({ type: "text", content: text.slice(lastIndex, match.index) });
    }
    if (match[1] !== undefined) {
      tokens.push({ type: "bold", content: match[1] });
    } else if (match[2] !== undefined) {
      tokens.push({ type: "italic", content: match[2] });
    } else if (match[3] !== undefined) {
      tokens.push({ type: "code", content: match[3] });
    } else if (match[4] !== undefined && match[5] !== undefined) {
      const href = match[5];
      // Only render internal paths as links; external URLs become text.
      if (href.startsWith("/")) {
        tokens.push({ type: "link", content: match[4], href });
      } else {
        tokens.push({ type: "text", content: match[4] });
      }
    }
    lastIndex = pattern.lastIndex;
  }
  if (lastIndex < text.length) {
    tokens.push({ type: "text", content: text.slice(lastIndex) });
  }
  return tokens;
}

function renderInline(tokens: Token[]): ReactNode[] {
  return tokens.map((token, i) => {
    switch (token.type) {
      case "bold":
        return <strong key={i}>{token.content}</strong>;
      case "italic":
        return <em key={i}>{token.content}</em>;
      case "code":
        return <code key={i} className="chat-md-code">{token.content}</code>;
      case "link":
        return (
          <a key={i} href={token.href} className="chat-md-link">
            {token.content}
          </a>
        );
      default:
        return <span key={i}>{token.content}</span>;
    }
  });
}

export function ChatMarkdown({ content }: { content: string }) {
  const lines = content.split("\n");
  const blocks: ReactNode[] = [];
  let listItems: string[] = [];
  let listOrdered = false;
  let key = 0;

  const flushList = () => {
    if (listItems.length === 0) return;
    const items = listItems.map((item, i) => (
      <li key={i}>{renderInline(parseInline(item))}</li>
    ));
    blocks.push(
      listOrdered ? (
        <ol key={key++} className="chat-md-list">
          {items}
        </ol>
      ) : (
        <ul key={key++} className="chat-md-list">
          {items}
        </ul>
      )
    );
    listItems = [];
  };

  for (const line of lines) {
    const trimmed = line.trim();
    // Headers
    if (trimmed.startsWith("### ")) {
      flushList();
      blocks.push(
        <h4 key={key++} className="chat-md-h4">
          {renderInline(parseInline(trimmed.slice(4)))}
        </h4>
      );
    } else if (trimmed.startsWith("## ")) {
      flushList();
      blocks.push(
        <h3 key={key++} className="chat-md-h3">
          {renderInline(parseInline(trimmed.slice(3)))}
        </h3>
      );
    } else if (trimmed.startsWith("# ")) {
      flushList();
      blocks.push(
        <h3 key={key++} className="chat-md-h3">
          {renderInline(parseInline(trimmed.slice(2)))}
        </h3>
      );
    } else if (trimmed.startsWith("- ") || trimmed.startsWith("* ")) {
      // Unordered list item
      if (listOrdered) flushList();
      listOrdered = false;
      listItems.push(trimmed.slice(2));
    } else if (/^\d+\.\s/.test(trimmed)) {
      // Ordered list item
      if (!listOrdered) flushList();
      listOrdered = true;
      listItems.push(trimmed.replace(/^\d+\.\s/, ""));
    } else if (trimmed === "") {
      flushList();
    } else {
      flushList();
      blocks.push(
        <p key={key++} className="chat-md-p">
          {renderInline(parseInline(trimmed))}
        </p>
      );
    }
  }
  flushList();

  return <div className="chat-md">{blocks}</div>;
}
