"use client";

import { Loader2 } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import {
  getPreferencesApiV1OrganizationsPreferencesGet,
  savePreferencesApiV1OrganizationsPreferencesPut,
} from "@/client/sdk.gen";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { detailFromError } from "@/lib/apiError";
import { useAuth } from "@/lib/auth";

type StorageMode = "everything" | "except_pii" | "basic_only";

const FOREVER = "forever";

const RETENTION = [
  { value: FOREVER, label: "Keep forever (default)" },
  { value: "30", label: "30 days" },
  { value: "60", label: "60 days" },
  { value: "90", label: "90 days" },
  { value: "180", label: "180 days" },
  { value: "365", label: "1 year" },
];

const MODES: { value: StorageMode; label: string }[] = [
  { value: "everything", label: "Keep everything" },
  { value: "except_pii", label: "Keep everything except personal details" },
  { value: "basic_only", label: "Keep basic details only" },
];

type Saved = { days: string; mode: StorageMode };

export function DataRetentionSection() {
  const { user, loading: authLoading } = useAuth();
  const hasFetched = useRef(false);

  const [saved, setSaved] = useState<Saved>({ days: FOREVER, mode: "everything" });
  const [days, setDays] = useState(FOREVER);
  const [mode, setMode] = useState<StorageMode>("everything");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [readOnly, setReadOnly] = useState(false);

  useEffect(() => {
    if (authLoading || !user || hasFetched.current) return;
    hasFetched.current = true;
    void load();
  }, [authLoading, user]);

  async function load() {
    setLoading(true);
    try {
      const response = await getPreferencesApiV1OrganizationsPreferencesGet();
      // The generated client resolves on HTTP errors instead of throwing.
      if (response.error) {
        setError(detailFromError(response.error, "Failed to load data retention"));
        return;
      }
      const prefs = response.data;
      const next: Saved = {
        days: prefs?.data_retention_days ? String(prefs.data_retention_days) : FOREVER,
        mode: (prefs?.default_storage_mode as StorageMode | undefined) ?? "everything",
      };
      setSaved(next);
      setDays(next.days);
      setMode(next.mode);
      setError(null);
    } catch (e) {
      setError(detailFromError(e, "Failed to load data retention"));
    } finally {
      setLoading(false);
    }
  }

  async function handleSave() {
    setSaving(true);
    try {
      const response = await savePreferencesApiV1OrganizationsPreferencesPut({
        // Only these two fields: the endpoint merges, so the rest of the
        // preferences are left exactly as they are. null is "keep forever".
        body: {
          data_retention_days: days === FOREVER ? null : Number(days),
          default_storage_mode: mode,
        },
      });
      if (response.error) {
        // A member gets 403. Say so rather than showing a generic failure next
        // to a control that looks editable.
        if (response.response?.status === 403) {
          setReadOnly(true);
          toast.error("Only an admin can change data retention.");
          return;
        }
        toast.error(detailFromError(response.error, "Could not save data retention"));
        return;
      }
      setSaved({ days, mode });
      toast.success("Saved. It applies to calls that start from now on.");
    } catch (e) {
      toast.error(detailFromError(e, "Could not save data retention"));
    } finally {
      setSaving(false);
    }
  }

  if (loading) {
    return (
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <Loader2 className="h-4 w-4 animate-spin" />
        Loading data retention…
      </div>
    );
  }

  if (error) return <p className="text-sm text-destructive">{error}</p>;

  const dirty = days !== saved.days || mode !== saved.mode;

  return (
    <div className="space-y-4">
      <div className="space-y-2">
        <Label className="text-xs">Delete a call&apos;s recording, transcript and logs after</Label>
        <Select value={days} onValueChange={setDays} disabled={readOnly}>
          <SelectTrigger className="max-w-sm">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {RETENTION.map((o) => (
              <SelectItem key={o.value} value={o.value}>
                {o.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <div className="space-y-2">
        <Label className="text-xs">What to keep, by default</Label>
        <Select
          value={mode}
          onValueChange={(v) => setMode(v as StorageMode)}
          disabled={readOnly}
        >
          <SelectTrigger className="max-w-sm">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {MODES.map((o) => (
              <SelectItem key={o.value} value={o.value}>
                {o.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <div className="space-y-1 text-xs text-muted-foreground">
        <p>
          These are the defaults for every agent. An agent can set its own under
          Data &amp; Safety in its settings.
        </p>
        <p>
          The deletion date is fixed when each call starts, so changing this does
          not affect calls that already happened. A call&apos;s outcome, duration
          and cost are always kept, so reports do not change. Nothing is deleted
          unless a period is set.
        </p>
      </div>

      <div className="flex items-center gap-3">
        <Button onClick={handleSave} disabled={saving || readOnly || !dirty}>
          {saving ? "Saving…" : "Save"}
        </Button>
        {readOnly && (
          <span className="text-xs text-muted-foreground">
            Only an admin can change this.
          </span>
        )}
      </div>
    </div>
  );
}
