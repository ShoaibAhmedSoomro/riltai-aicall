import { cn } from "@/lib/utils";

// Reusable RiltAI lockup, served as SVG so it stays crisp at any size.
//
// The artwork is monochrome, which makes the theme pairing load-bearing rather
// than decorative: every variant needs BOTH an ink and a white file, because
// solid ink on a dark surface is invisible rather than merely low-contrast.
// (The previous two-tone mark survived a missing switch by accident -- its
// coloured half still showed. This one would not.)
//
//   default  theme-paired via dark: variants — ink on light, white on dark
//   inverse  forces the white lockup for an always-dark surface (auth panel)
//   mark     the monogram alone, also theme-paired (collapsed sidebar header)
//
// Height comes from the caller via className (e.g. "h-7"); width stays auto so
// each file keeps its own aspect ratio — the lockup is wide, the mark is tall.
export function BrandLogo({
  className,
  inverse = false,
  mark = false,
}: {
  className?: string;
  inverse?: boolean;
  mark?: boolean;
}) {
  const alt = "RiltAI";

  if (mark) {
    return (
      <>
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src="/rilt-mark.svg" alt={alt} className={cn("block w-auto select-none dark:hidden", className)} />
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src="/rilt-mark-inverse.svg" alt="" aria-hidden className={cn("hidden w-auto select-none dark:block", className)} />
      </>
    );
  }

  if (inverse) {
    return (
      // eslint-disable-next-line @next/next/no-img-element
      <img src="/rilt-logo-inverse.svg" alt={alt} className={cn("w-auto select-none", className)} />
    );
  }

  return (
    <>
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src="/rilt-logo.svg" alt={alt} className={cn("block w-auto select-none dark:hidden", className)} />
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src="/rilt-logo-inverse.svg" alt="" aria-hidden className={cn("hidden w-auto select-none dark:block", className)} />
    </>
  );
}
