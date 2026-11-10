"use client";

import { useEffect, useRef } from "react";
import { usePathname, useRouter } from "next/navigation";
import gsap from "gsap";
import { Mark } from "./brand";

export function PublicMotion() {
  const router = useRouter();
  const pathname = usePathname();
  const wipe = useRef<HTMLDivElement>(null);
  const intro = useRef<HTMLDivElement>(null);
  const finish = useRef<(() => void) | null>(null);

  useEffect(() => {
    finish.current?.();
  }, [pathname]);

  useEffect(() => {
    const overlay = wipe.current;
    const path = overlay?.querySelector("path");
    if (!overlay || !path) return;
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)");
    let timeline: gsap.core.Timeline | undefined;
    let timeout: number | undefined;
    let active = false;

    const click = (event: MouseEvent) => {
      if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey || reduced.matches) return;
      const link = event.target instanceof Element ? event.target.closest("a[href]") : null;
      if (!(link instanceof HTMLAnchorElement) || link.target || link.hasAttribute("download")) return;
      const next = new URL(link.href);
      const current = window.location.pathname;
      if (next.origin !== window.location.origin || !["/", "/login"].includes(next.pathname) || !["/", "/login"].includes(current) || current === next.pathname) return;
      event.preventDefault();
      if (active) return;
      active = true;
      finish.current = () => {
        finish.current = null;
        window.clearTimeout(timeout);
        timeline?.kill();
        timeline = gsap.timeline({ onComplete: () => { active = false; } });
        timeline.to(overlay, { clipPath: "inset(0 0 0 100%)", duration: 0.45, ease: "power2.inOut" })
          .set(overlay, { clearProps: "all" })
          .set(path, { clearProps: "all" });
      };
      timeline = gsap.timeline({ onComplete: () => {
        timeout = window.setTimeout(() => finish.current?.(), 2500);
        router.push(next.pathname + next.search + next.hash);
      } });
      timeline.set(overlay, { visibility: "visible", pointerEvents: "auto" })
        .fromTo(path, { strokeDashoffset: 1 }, { strokeDashoffset: 0, duration: 0.65, ease: "power2.inOut" })
        .to(overlay, { backgroundColor: "#2948f5", duration: 0.2 }, "-=.18");
    };

    document.addEventListener("click", click, true);
    return () => {
      document.removeEventListener("click", click, true);
      timeline?.kill();
      window.clearTimeout(timeout);
      finish.current = null;
      gsap.set([overlay, path], { clearProps: "all" });
    };
  }, [router]);

  useEffect(() => {
    const element = intro.current;
    if (!element || window.location.pathname !== "/" || window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    try {
      if (sessionStorage.getItem("knotdevt-intro")) return;
    } catch { return; }
    const animation = gsap.timeline({ onComplete: () => {
      try { sessionStorage.setItem("knotdevt-intro", "seen"); } catch { /* storage unavailable */ }
    } }).set(element, { visibility: "visible" })
      .fromTo(element.querySelector("path"), { strokeDashoffset: 1 }, { strokeDashoffset: 0, duration: 0.56 })
      .to(element, { opacity: 0, duration: 0.36 })
      .set(element, { visibility: "hidden" });
    return () => { animation.kill(); gsap.set(element, { clearProps: "all" }); };
  }, []);

  return (
    <>
      <div ref={intro} className="public-intro" aria-hidden="true"><Mark /><span>KnotDevt.</span></div>
      <div ref={wipe} className="route-wipe" aria-hidden="true">
        <svg viewBox="0 0 1000 800" preserveAspectRatio="none">
          <path pathLength="1" d="M-170 35C190 75 720-135 1130 75S1330 320 875 310S-245 126-120 422S880 370 1070 530S960 810 460 687S-170 690-95 880" />
        </svg>
      </div>
    </>
  );
}
