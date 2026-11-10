"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import {
  ArrowDown,
  ArrowDownRight,
  ArrowRight,
  ArrowUpRight,
  GitBranch,
  FileText,
  ShieldCheck,
} from "lucide-react";
import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import Lenis from "lenis";
import { Brand, Mark } from "./brand";

const stages = [
  [
    "Collect",
    "Bring permitted issues and conversation notes into the same thread.",
    "Sources / revision snapshot",
  ],
  [
    "Map",
    "Surface why decisions were made and what work remains unfinished.",
    "Decisions / open work",
  ],
  [
    "Verify",
    "Check exact evidence spans and surface conflicting or missing support.",
    "Evidence / audit",
  ],
  [
    "Review",
    "Have a reviewer confirm critical gaps, ownership and approvals.",
    "Human checkpoint / required",
  ],
  [
    "Deliver",
    "Give the next teammate a scoped handover and a readiness rehearsal.",
    "Handover / readiness",
  ],
];
const fragments = [
  ["ISSUE · PAY-21", "Friday release proposed.", "Proposal"],
  ["CHANGE · C-19", "The payment change was merged.", "Implementation"],
  [
    "NOTE · M-07",
    "Monday approved, pending testing sign-off.",
    "Conditional approval",
  ],
];
const chronology = [
  ["01", "Friday proposed", "PAY-21", "A deployment date was discussed."],
  [
    "02",
    "Code merged",
    "C-19",
    "The implementation landed. Release still needed approval.",
  ],
  [
    "03",
    "Monday, conditional",
    "M-07",
    "Monday was approved subject to testing sign-off.",
  ],
  ["04", "Sign-off unresolved", "M-07", "Testing approval was still missing."],
  [
    "05",
    "Rollback owner missing",
    "M-07",
    "The team had yet to assign rollback ownership.",
  ],
];
const dispositions = [
  [
    "Blocking",
    "Testing sign-off is required before release.",
    "Missing approval",
  ],
  ["Unverified", "A reviewer needs to confirm who owns rollback.", "Ownership"],
  [
    "Resolved",
    "A later source records the approval and identifies the approver.",
    "Evidence-backed resolution",
  ],
  ["Non-critical", "Clean up the follow-up notes after release.", "Work item"],
];

export default function Landing() {
  const root = useRef<HTMLDivElement>(null);
  const [example, setExample] = useState(2);
  const [disposition, setDisposition] = useState(0);

  useEffect(() => {
    gsap.registerPlugin(ScrollTrigger);
    const context = gsap.matchMedia(root);
    context.add(
      "(min-width: 900px) and (pointer: fine) and (prefers-reduced-motion: no-preference)",
      () => {
        const lenis = new Lenis({ lerp: 0.165, wheelMultiplier: 1.25 });
        const tick = (time: number) => lenis.raf(time * 1000);
        lenis.on("scroll", ScrollTrigger.update);
        gsap.ticker.add(tick);
        const reel = gsap.to(".marquee-track", {
          xPercent: -50,
          duration: 28,
          repeat: -1,
          ease: "none",
        });
        // Leave enough timeline on either side for direction changes.
        reel.totalTime(reel.duration() * 100);
        ScrollTrigger.create({
          trigger: ".marquee",
          onUpdate: (self) => reel.timeScale(self.direction),
        });
        gsap.to(".fragment:nth-child(odd)", {
          y: -55,
          rotate: -4,
          scrollTrigger: { trigger: ".fragments", scrub: true },
        });
        gsap.to(".fragment:nth-child(even)", {
          y: 40,
          rotate: 3,
          scrollTrigger: { trigger: ".fragments", scrub: true },
        });
        gsap.fromTo(
          ".footer-word",
          { yPercent: 20, opacity: 0.72 },
          {
            yPercent: 0,
            opacity: 0.9,
            ease: "none",
            scrollTrigger: {
              trigger: ".public-footer",
              start: "top 90%",
              end: "bottom bottom",
              scrub: true,
            },
          },
        );
        gsap.fromTo(
          ".history-line path",
          { strokeDashoffset: 1 },
          {
            strokeDashoffset: 0,
            ease: "none",
            scrollTrigger: {
              trigger: ".history",
              start: "top 83%",
              end: "center 55%",
              scrub: true,
            },
          },
        );
        const cards = gsap.utils.toArray<HTMLElement>(".story-card");
        gsap.set(cards, {
          y: (index) => index * 24,
          z: (index) => -index * 80,
          scale: (index) => 1 - index * 0.05,
          zIndex: (index) => cards.length - index,
        });
        const timeline = gsap.timeline({
          scrollTrigger: {
            trigger: ".story",
            start: "top top",
            end: "+=155%",
            pin: true,
            scrub: 0.45,
          },
        });
        cards.slice(0, -1).forEach((card, index) => {
          timeline.to(
            card,
            { yPercent: -75, autoAlpha: 0, scale: 0.92, duration: 1 },
            index,
          );
          cards.slice(index + 1).forEach((behind, depth) => {
            timeline.to(
              behind,
              {
                y: depth * 24,
                z: -depth * 80,
                scale: 1 - depth * 0.05,
                duration: 1,
              },
              index,
            );
          });
        });
        const glow = root.current?.querySelector<HTMLElement>(".cursor-glow");
        const glowX = glow && gsap.quickTo(glow, "x", { duration: 0.28 });
        const glowY = glow && gsap.quickTo(glow, "y", { duration: 0.28 });
        const stack = root.current?.querySelector<HTMLElement>(".stack");
        const tiltX =
          stack && gsap.quickTo(stack, "rotateX", { duration: 0.6 });
        const tiltY =
          stack && gsap.quickTo(stack, "rotateY", { duration: 0.6 });
        const follow = (event: PointerEvent) => {
          if (event.pointerType === "touch") return;
          if (glow) gsap.set(glow, { opacity: 1 });
          glowX?.(event.clientX);
          glowY?.(event.clientY);
          tiltX?.((0.5 - event.clientY / innerHeight) * 5);
          tiltY?.((event.clientX / innerWidth - 0.5) * 7);
        };
        window.addEventListener("pointermove", follow, { passive: true });
        return () => {
          window.removeEventListener("pointermove", follow);
          gsap.ticker.remove(tick);
          lenis.destroy();
        };
      },
    );
    return () => context.revert();
  }, []);

  return (
    <div ref={root} className="landing">
      <header className="site-nav">
        <Brand />
        <nav aria-label="Main navigation">
          <a href="#how">How it works</a>
          <a href="#evidence">Evidence</a>
        </nav>
        <Link href="/login" className="button button-blue">
          Login <ArrowUpRight size={17} />
        </Link>
      </header>
      <main>
        <section className="hero public-pad">
          <div className="hero-copy">
            <div className="eyebrow">
              <span className="blue-dot" /> HANDOVER INTELLIGENCE{" "}
              <span className="tag">K0.1.0</span>
            </div>
            <h1>
              <span>Knowledge</span>
              <span>shouldn’t leave</span>
              <span>
                <i>with people.</i>
              </span>
            </h1>
            <p>
              Turn scattered project activity into an evidence-backed handover
              your next teammate can actually trust.
            </p>
            <div className="hero-actions">
              <Link
                href="/login"
                className="button button-blue"
              >
                Enter workspace <ArrowUpRight size={18} />
              </Link>
              <a className="text-link" href="#how">
                Explore the platform <ArrowDown size={17} />
              </a>
            </div>
          </div>
          <div className="hero-art" aria-hidden="true">
            <div className="art-meta">
              <span>FIG. 01 / THE HANDOVER</span>
              <span>+</span>
            </div>
            <svg viewBox="0 0 640 550" preserveAspectRatio="xMidYMid meet">
              <defs>
                <pattern
                  id="art-grid"
                  width="32"
                  height="32"
                  patternUnits="userSpaceOnUse"
                >
                  <path
                    d="M32 0H0V32"
                    fill="none"
                    stroke="#9eb4ff"
                    strokeOpacity=".23"
                  />
                </pattern>
              </defs>
              <rect width="640" height="550" fill="url(#art-grid)" />
              <g fill="none" strokeLinecap="round">
                <path
                  d="M-40 390C130 390 169 140 312 140S486 375 685 375"
                  stroke="#7493ff"
                  strokeWidth="50"
                  opacity=".45"
                />
                <path
                  className="hero-thread"
                  pathLength="1"
                  d="M-40 390C130 390 169 140 312 140S486 375 685 375"
                  stroke="#e8edff"
                  strokeWidth="14"
                />
                <path
                  className="hero-thread second"
                  pathLength="1"
                  d="M-40 220C130 220 169 428 312 428S486 201 685 201"
                  stroke="#a2b7ff"
                  strokeWidth="13"
                />
                <path
                  d="M62 470V66h505v404z"
                  stroke="#9eb4ff"
                  strokeDasharray="3 8"
                  opacity=".6"
                />
              </g>
              <g fill="#f5f2eb" stroke="#2948f5" strokeWidth="6">
                <circle cx="140" cy="327" r="13" />
                <circle cx="320" cy="141" r="13" />
                <circle cx="496" cy="320" r="13" />
              </g>
            </svg>
            <div className="art-card art-source">
              <GitBranch size={17} />{" "}
              <span>
                PAY-21
                <br />
                <small>Decision proposed</small>
              </span>
            </div>
            <div className="art-card art-review">
              <ShieldCheck size={18} />{" "}
              <span>
                REVIEW
                <br />
                <small>Sign-off pending</small>
              </span>
            </div>
            <div className="art-meta art-bottom">
              <span>CONTEXT → EVIDENCE → HANDOVER</span>
              <ArrowDownRight size={17} />
            </div>
          </div>
        </section>
        <div className="marquee" aria-hidden="true">
          <div className="marquee-track">
            {[0, 1].map((n) => (
              <span key={n}>
                KEEP THE THREAD <b>✳</b> KEEP THE THREAD <b>✳</b>&nbsp;
              </span>
            ))}
          </div>
        </div>
        <section className="problem public-pad">
          <div className="eyebrow">01 / THE PROBLEM</div>
          <h2>
            The work is documented.
            <br />
            <i>The reasons aren’t.</i>
          </h2>
          <p>
            A merge, an issue, and a meeting note can tell very different parts
            of the same story.
          </p>
          <div className="fragments">
            {fragments.map(([ref, note, type], index) => (
              <article className="fragment" key={ref}>
                <div className="eyebrow">
                  <FileText size={15} />
                  {ref}
                </div>
                <h3>{note}</h3>
                <span>{type}</span>
                <a
                  className="fragment-preview"
                  href="#evidence"
                  onClick={() => setExample(index)}
                  aria-label={`Inspect evidence for ${ref}`}
                >
                  Preview citation <ArrowUpRight size={15} aria-hidden="true" />
                </a>
              </article>
            ))}
          </div>
        </section>
        <section id="how" className="story public-pad">
          <div>
            <div className="eyebrow">02 / THE WORKFLOW</div>
            <h2>
              From loose ends
              <br />
              <i>to a clear handover.</i>
            </h2>
            <p>Five steps. Every handover passes through human review.</p>
          </div>
          <div className="stack">
            {stages.map(([title, body, meta], index) => (
              <article className="story-card" key={title}>
                <div className="eyebrow">
                  STEP 0{index + 1} <ArrowDownRight size={18} />
                </div>
                <h3>{title}</h3>
                <p>{body}</p>
                <small>{meta}</small>
              </article>
            ))}
          </div>
        </section>
        <section id="evidence" className="public-evidence public-pad">
          <div>
            <div className="eyebrow">03 / EVIDENCE & CONTEXT TRACE</div>
            <h2>
              Every important claim <i>has a source.</i>
            </h2>
            <p>
              Follow the chronology from proposal to conditional approval, then
              inspect the source behind each step.
            </p>
          </div>
          <div className="sample panel">
            <div className="eyebrow">SYNTHETIC EXAMPLE</div>
            <div className="sample-tabs">
              {fragments.map(([ref], index) => (
                <button
                  key={ref}
                  aria-pressed={example === index}
                  onClick={() => setExample(index)}
                >
                  {ref}
                </button>
              ))}
            </div>
            <div key={example} className="enter">
              <small>{fragments[example][2]}</small>
              <h3>{fragments[example][1]}</h3>
              <p>Illustrative source revision · rev 01</p>
            </div>
          </div>
        </section>
        <section className="history public-pad">
          <div className="eyebrow">04 / SYNTHETIC DECISION HISTORY</div>
          <h2>
            Decisions <i>have history.</i>
          </h2>
          <div className="history-track">
            <svg
              className="history-line"
              viewBox="0 0 1000 100"
              preserveAspectRatio="none"
              aria-hidden="true"
            >
              <path
                pathLength="1"
                d="M10 56C130 12 215 86 307 50S460 7 554 48S660 87 742 53S895 12 990 52"
                fill="none"
                stroke="currentColor"
                strokeWidth="3"
              />
            </svg>
            <ol>
              {chronology.map(([step, title, source, detail]) => (
                <li key={step}>
                  <div className="history-node">{step}</div>
                  <span className="eyebrow">{source}</span>
                  <h3>{title}</h3>
                  <p>{detail}</p>
                </li>
              ))}
            </ol>
          </div>
        </section>
        <section className="public-evidence human-review public-pad">
          <div>
            <div className="eyebrow">05 / THE HUMAN CHECKPOINT</div>
            <h2>
              AI finds the threads.
              <br />
              <i>People verify the truth.</i>
            </h2>
            <p>
              Reviewers record the disposition of critical gaps against the
              exact sources and claims in the draft.
            </p>
          </div>
          <div className="sample panel">
            <div className="eyebrow">SYNTHETIC REVIEW</div>
            <div className="sample-tabs">
              {dispositions.map(([title], index) => (
                <button
                  key={title}
                  aria-pressed={disposition === index}
                  onClick={() => setDisposition(index)}
                >
                  {title}
                </button>
              ))}
            </div>
            <div key={disposition} className="enter">
              <small>{dispositions[disposition][2]}</small>
              <h3>{dispositions[disposition][0]}</h3>
              <p>{dispositions[disposition][1]}</p>
            </div>
          </div>
        </section>
        <section className="readiness-story public-pad">
          <div>
            <div className="eyebrow">06 / READINESS WITH CONTEXT</div>
            <h2>
              Know where
              <br />
              <i>you stand.</i>
            </h2>
            <p>
              A reviewer checks the project’s approvals, prerequisites and
              ownership. The rehearsal measures what the recipient understands.
            </p>
          </div>
          <div className="score-demo">
            <small>SYNTHETIC ASSESSMENT</small>
            <strong>
              100<span>/100</span>
            </strong>
            <b>Blocked by project gap</b>
            <p>Testing sign-off is still required.</p>
          </div>
        </section>
        <footer className="public-footer public-pad">
          <div className="eyebrow">
            <Mark /> THE NEXT HANDOVER STARTS HERE
          </div>
          <h2>
            Make every handover
            <br />
            <i>a stronger start.</i>
          </h2>
          <div className="hero-actions">
            <Link
              className="button button-white"
              href="/login"
            >
              Open KnotDevt <ArrowUpRight size={18} />
            </Link>
            <a className="text-link" href="#how">
              Explore how it works <ArrowRight size={17} />
            </a>
          </div>
          <div className="footer-word" aria-hidden="true">
            KnotDevt<span>.</span>
          </div>
        </footer>
      </main>
      <div className="cursor-glow" aria-hidden="true" />
    </div>
  );
}
