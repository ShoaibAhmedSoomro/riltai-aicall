"use client";

import { MailCheck } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import {
  getCurrentUserApiV1AuthMeGet,
  resendVerificationApiV1AuthResendVerificationPost,
} from "@/client/sdk.gen";
import { Button } from "@/components/ui/button";
import { detailFromError } from "@/lib/apiError";
import { useAuth } from "@/lib/auth";

/**
 * Shown only to a signed-in user whose address has not been verified.
 *
 * Renders nothing in every other case, including while loading and when the
 * lookup fails. A banner that flashes for verified users, or appears because a
 * request errored, would claim something about their account that the server
 * never said.
 *
 * Nothing in the product is gated on this. It is informational, so it is a
 * notice with a button, not a wall.
 */
export function EmailVerificationNotice() {
  const { user, loading: authLoading } = useAuth();
  const hasFetched = useRef(false);
  const [unverified, setUnverified] = useState(false);
  const [sending, setSending] = useState(false);
  const [sent, setSent] = useState(false);

  useEffect(() => {
    if (authLoading || !user || hasFetched.current) return;
    hasFetched.current = true;

    getCurrentUserApiV1AuthMeGet().then((res) => {
      // Only an explicit false counts. Missing or errored is "unknown", and
      // unknown is not unverified.
      if (!res.error && res.data?.email_verified === false) {
        setUnverified(true);
      }
    });
  }, [authLoading, user]);

  async function handleResend() {
    setSending(true);
    try {
      const res = await resendVerificationApiV1AuthResendVerificationPost();
      if (res.error) {
        // 503 (email not configured) and 502 (provider refused) both carry a
        // plain explanation, which is exactly what should be shown.
        toast.error(detailFromError(res.error, "Could not send the email."));
        return;
      }
      if (res.data?.status === "already_verified") {
        setUnverified(false);
        return;
      }
      setSent(true);
    } catch (err) {
      toast.error(detailFromError(err, "Could not send the email."));
    } finally {
      setSending(false);
    }
  }

  if (!unverified) return null;

  return (
    <div className="flex items-start gap-3 rounded-md border border-border bg-muted/40 p-4 text-sm">
      <MailCheck className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
      <div className="flex-1 space-y-2">
        <p>
          <span className="font-medium">Your email address isn&apos;t verified.</span>{" "}
          <span className="text-muted-foreground">
            Confirm it so we can reach you about your account.
          </span>
        </p>
        {sent ? (
          <p className="text-muted-foreground">
            Sent. Check your inbox for the link.
          </p>
        ) : (
          <Button size="sm" variant="outline" onClick={handleResend} disabled={sending}>
            {sending ? "Sending…" : "Send verification email"}
          </Button>
        )}
      </div>
    </div>
  );
}
