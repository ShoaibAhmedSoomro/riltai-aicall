import { Suspense } from "react";

import { ResetPasswordForm } from "./ResetPasswordForm";

// useSearchParams needs a Suspense boundary, or `next build` fails the whole
// route with a prerender error rather than degrading.
export default function ResetPasswordPage() {
  return (
    <Suspense>
      <ResetPasswordForm />
    </Suspense>
  );
}
