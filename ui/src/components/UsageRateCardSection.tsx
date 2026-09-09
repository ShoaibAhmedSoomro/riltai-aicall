"use client";

import { Loader2 } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import {
  getUsageRateCardApiV1OrganizationsUsageRateCardGet,
  saveUsageRateCardApiV1OrganizationsUsageRateCardPut,
} from "@/client/sdk.gen";
import type { UsageRateCardResponse } from "@/client/types.gen";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { detailFromError } from "@/lib/apiError";
import { useAuth } from "@/lib/auth";

export function UsageRateCardSection() {
  const { user, loading: authLoading } = useAuth();
  const hasFetched = useRef(false);

  const [card, setCard] = useState<UsageRateCardResponse | null>(null);
  const [rate, setRate] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [readOnly, setReadOnly] = useState(false);

  useEffect(() => {
    if (authLoading || !user || hasFetched.current) {
      return;
    }
    hasFetched.current = true;
    void fetchCard();
  }, [authLoading, user]);

  async function fetchCard() {
    setLoading(true);
    try {
      const response = await getUsageRateCardApiV1OrganizationsUsageRateCardGet();
      // The generated client resolves on HTTP errors rather than throwing, so
      // an unchecked failure would render as "no price set" — which is a claim,
      // not a failure.
      if (response.error) {
        setError(detailFromError(response.error, "Failed to load the rate card"));
        return;
      }
      const data = response.data ?? null;
      setCard(data);
      setRate(
        data?.price_per_minute_usd != null
          ? String(data.price_per_minute_usd)
          : "",
      );
      setError(null);
    } catch (e) {
      setError(detailFromError(e, "Failed to load the rate card"));
    } finally {
      setLoading(false);
    }
  }

  async function handleSave() {
    const parsed = Number(rate);
    if (!Number.isFinite(parsed) || parsed <= 0) {
      toast.error("Enter a price greater than zero.");
      return;
    }
    setSaving(true);
    try {
      const response = await saveUsageRateCardApiV1OrganizationsUsageRateCardPut({
        body: { price_per_minute_usd: parsed, currency: card?.currency || "USD" },
      });
      if (response.error) {
        // A member gets 403 here. Say so rather than showing a generic failure
        // next to a control that looks editable.
        if (response.response?.status === 403) {
          setReadOnly(true);
          toast.error("Only an admin can change the rate.");
          return;
        }
        toast.error(detailFromError(response.error, "Could not save the rate"));
        return;
      }
      setCard(response.data ?? null);
      toast.success("Rate saved. It applies to calls completed from now on.");
    } catch (e) {
      toast.error(detailFromError(e, "Could not save the rate"));
    } finally {
      setSaving(false);
    }
  }

  if (loading) {
    return (
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <Loader2 className="h-4 w-4 animate-spin" />
        Loading rate card…
      </div>
    );
  }

  if (error) {
    return <p className="text-sm text-destructive">{error}</p>;
  }

  // On the hosted plan MPS prices every call and this value is ignored
  // entirely. Showing an editable box there would be a control that does
  // nothing, which is worse than no control.
  if (card && !card.applies_to_this_deployment) {
    return (
      <p className="text-sm text-muted-foreground">
        Calls on this plan are priced by AICall, so there is no local rate to
        set. Your usage and spend come from your billing account.
      </p>
    );
  }

  const dirty =
    rate.trim() !== "" &&
    Number(rate) !== (card?.price_per_minute_usd ?? Number.NaN);

  return (
    <div className="space-y-4">
      <div className="space-y-2">
        <Label htmlFor="price_per_minute_usd" className="text-xs">
          Price per minute (USD)
        </Label>
        <div className="flex items-center gap-2">
          <Input
            id="price_per_minute_usd"
            type="number"
            step="0.001"
            min="0"
            max="100"
            placeholder="e.g. 0.05"
            value={rate}
            disabled={readOnly}
            onChange={(e) => setRate(e.target.value)}
            className="max-w-[180px]"
          />
          <Button onClick={handleSave} disabled={saving || readOnly || !dirty}>
            {saving ? "Saving…" : "Save rate"}
          </Button>
        </div>
      </div>

      <div className="space-y-1 text-xs text-muted-foreground">
        {card?.configured ? (
          <p>
            Calls are costed at{" "}
            <span className="font-medium text-foreground">
              ${card.price_per_minute_usd}/min
            </span>
            . Only calls completed after a change use the new rate — existing
            calls keep what they were costed at, so a report does not change
            retroactively.
          </p>
        ) : (
          <p>
            <span className="font-medium text-foreground">No price set.</span>{" "}
            Cost columns and spend figures stay empty until you set one. They
            show empty rather than $0.00 on purpose: zero would say your calls
            were free.
          </p>
        )}
        {readOnly && <p>Only an admin can change the rate.</p>}
      </div>
    </div>
  );
}
