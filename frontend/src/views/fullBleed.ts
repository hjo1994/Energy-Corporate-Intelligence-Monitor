import { useEffect } from "react";

/** The agreed Start and Exploration pages span the whole window below the top bar: while one is shown, the page
 * clips horizontal overflow (so the full-bleed bands cause no sideways scroll) and takes the view's background. */
export function useFullBleed(background?: string) {
  useEffect(() => {
    const html = document.documentElement;
    html.classList.add("full-bleed");
    const before = document.body.style.background;
    if (background) document.body.style.background = background;
    return () => {
      html.classList.remove("full-bleed");
      document.body.style.background = before;
    };
  }, [background]);
}
