import { Suspense } from "react";

import { VerifyEmail } from "./VerifyEmail";

// useSearchParams needs a Suspense boundary, or `next build` fails the route
// outright rather than degrading.
export default function VerifyEmailPage() {
  return (
    <Suspense>
      <VerifyEmail />
    </Suspense>
  );
}
