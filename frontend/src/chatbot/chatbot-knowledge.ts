/**
 * Context-aware greetings and suggested questions for the KnotDevt guide chatbot.
 *
 * These are deterministic interface text, NOT model-generated content.
 * Each greeting adapts to the user's current page and is shown when the
 * chatbot panel first opens.
 */

export interface PageGreeting {
  greeting: string;
  questions: string[];
}

const GREETINGS: Record<string, PageGreeting> = {
  landing: {
    greeting: "Welcome to KnotDevt. I can explain how our project handover platform works.",
    questions: [
      "What is KnotDevt?",
      "How does the handover process work?",
      "What are the five AI agents?",
    ],
  },
  login: {
    greeting: "Welcome to KnotDevt. Sign in or create an account to get started.",
    questions: [
      "How do I create an account?",
      "What can I do after signing in?",
      "What is KnotDevt?",
    ],
  },
  overview: {
    greeting: "Welcome to your workspace. I can help you navigate KnotDevt.",
    questions: [
      "How do I create a project?",
      "How do I invite a recipient?",
      "What is the five-agent workflow?",
    ],
  },
  projects: {
    greeting: "Need help creating a project or inviting a recipient?",
    questions: [
      "How do I create a project?",
      "How do I invite a teammate?",
      "How do I assign a recipient role?",
    ],
  },
  sources: {
    greeting: "I can guide you through importing and organizing project evidence.",
    questions: [
      "How do I import sources?",
      "What source formats are supported?",
      "What are source revisions?",
    ],
  },
  agents: {
    greeting: "Want to understand the five execution stages or troubleshoot a job?",
    questions: [
      "What are the five agents?",
      "How does the workflow progress?",
      "What does a failed job mean?",
    ],
  },
  evidence: {
    greeting: "I can help you understand claims, citations, and the evidence graph.",
    questions: [
      "What is the Evidence Explorer?",
      "How do claims link to sources?",
      "What are citation spans?",
    ],
  },
  review: {
    greeting: "I can explain how to verify claims and approve a handover.",
    questions: [
      "How do I review claims?",
      "What is the critical-gap review?",
      "How do I publish a handover?",
    ],
  },
  versions: {
    greeting: "I can help you understand version publishing and stale versions.",
    questions: [
      "What is a published handover version?",
      "What makes a version stale?",
      "How are versions made immutable?",
    ],
  },
  readiness: {
    greeting: "I can help you understand the recipient assessment process.",
    questions: [
      "What is the Readiness Test?",
      "How does the Context Trace work?",
      "What does receipt acknowledgement mean?",
    ],
  },
};

const DEFAULT_GREETING: PageGreeting = {
  greeting: "Welcome to KnotDevt. I'm here to help you navigate the platform.",
  questions: [
    "What is KnotDevt?",
    "How does the handover process work?",
    "What are the five AI agents?",
  ],
};

/**
 * Detect the current page context from the browser URL.
 * Returns a page identifier that maps to a greeting.
 */
export function detectPageContext(): string {
  if (typeof window === "undefined") return "landing";
  const pathname = window.location.pathname;
  if (pathname === "/" || pathname === "") return "landing";
  if (pathname === "/login") return "login";
  if (pathname === "/app" || pathname.startsWith("/app")) {
    const params = new URLSearchParams(window.location.search);
    const view = params.get("view");
    if (view && view in GREETINGS) return view;
    return "overview";
  }
  return "overview";
}

export function getGreeting(pageContext: string): PageGreeting {
  return GREETINGS[pageContext] ?? DEFAULT_GREETING;
}
