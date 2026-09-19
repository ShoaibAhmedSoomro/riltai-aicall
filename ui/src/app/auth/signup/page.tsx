import { Suspense } from "react";

import { SignupForm } from "./SignupForm";

// useSearchParams needs a Suspense boundary, or `next build` fails the route
// outright rather than degrading.
export default function SignupPage() {
  return (
    <Suspense>
      <SignupForm />
    </Suspense>
  );
}
