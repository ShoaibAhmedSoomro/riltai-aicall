import { cn } from "@/lib/utils";

// Reusable Social Cangaroo wordmark, served as SVG so it stays crisp at any
// size. Theme-aware by default: the #2b2b2b wordmark shows on light surfaces
// and the white one on dark. Pass `inverse` to force the white lockup on an
// always-dark surface (e.g. the auth brand panel). Pass `mark` to render the
// two-tone kangaroo mark alone instead of the full lockup (e.g. the collapsed
// sidebar header). Height is controlled by the caller via className (e.g.
// "h-7"); width stays auto so each lockup keeps its aspect ratio.
export function BrandLogo({
  className,
  inverse = false,
  mark = false,
}: {
  className?: string;
  inverse?: boolean;
  mark?: boolean;
}) {
  if (mark) {
    return (
      // eslint-disable-next-line @next/next/no-img-element
      <img src="/social-cangaroo-mark.svg" alt="Social Cangaroo" className={cn("w-auto select-none", className)} />
    );
  }
  if (inverse) {
    return (
      // eslint-disable-next-line @next/next/no-img-element
      <img src="/social-cangaroo-logo-inverse.svg" alt="Social Cangaroo" className={cn("w-auto select-none", className)} />
    );
  }
  return (
    <>
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src="/social-cangaroo-logo.svg" alt="Social Cangaroo" className={cn("block w-auto select-none dark:hidden", className)} />
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src="/social-cangaroo-logo-inverse.svg" alt="Social Cangaroo" className={cn("hidden w-auto select-none dark:block", className)} />
    </>
  );
}
