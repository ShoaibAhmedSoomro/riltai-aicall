"use client";

import { CheckCircle2, Download, Loader2, XCircle } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import CsvUploadSelector from "@/app/campaigns/CsvUploadSelector";
import {
    createContactListApiV1ContactsListsPost,
    getImportApiV1ContactsImportsImportUuidGet,
    getImportErrorReportUrlApiV1ContactsImportsImportUuidErrorReportUrlGet,
    importContactsApiV1ContactsImportPost,
    importSuppressionsApiV1ContactsSuppressionsImportPost,
    previewImportApiV1ContactsImportPreviewGet,
} from "@/client/sdk.gen";
import type { ContactImportResponse, ContactListResponse } from "@/client/types.gen";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { detailFromError } from "@/lib/apiError";

import { fieldNameFromHeader, guessColumns, importSummary, validateFieldName } from "./utils";

const NONE = "__none__";
const POLL_MS = 1500;
const POLL_LIMIT_MS = 10 * 60 * 1000;

type Step = "upload" | "map" | "running" | "done";
type Preview = { headers: string[]; rows: string[][] };
type Extra = { include: boolean; name: string };

/**
 * Bring contacts in from a CSV, or (mode "suppression") load a do-not-call file.
 * The same three steps either way: pick the file, say which column is which,
 * watch it run. Rows that cannot be used are collected into a file you can fix
 * and re-import; they never stop the rest.
 */
export function ContactImportDialog({
    open,
    onOpenChange,
    onDone,
    lists = [],
    mode = "contacts",
}: {
    open: boolean;
    onOpenChange: (open: boolean) => void;
    onDone: () => void;
    lists?: ContactListResponse[];
    mode?: "contacts" | "suppression";
}) {
    const suppression = mode === "suppression";
    const [step, setStep] = useState<Step>("upload");
    const [fileKey, setFileKey] = useState("");
    const [fileName, setFileName] = useState("");
    const [preview, setPreview] = useState<Preview | null>(null);
    const [loadingPreview, setLoadingPreview] = useState(false);

    const [phoneCol, setPhoneCol] = useState("");
    const [firstCol, setFirstCol] = useState(NONE);
    const [lastCol, setLastCol] = useState(NONE);
    const [emailCol, setEmailCol] = useState(NONE);
    const [extras, setExtras] = useState<Record<string, Extra>>({});
    const [country, setCountry] = useState("");
    const [listChoice, setListChoice] = useState(NONE);
    const [newList, setNewList] = useState("");
    const [strategy, setStrategy] = useState<"skip" | "update">("skip");

    const [submitting, setSubmitting] = useState(false);
    const [progress, setProgress] = useState<ContactImportResponse | null>(null);
    const [error, setError] = useState<string | null>(null);
    const poll = useRef<ReturnType<typeof setTimeout> | null>(null);

    useEffect(() => () => { if (poll.current) clearTimeout(poll.current); }, []);

    function reset() {
        if (poll.current) clearTimeout(poll.current);
        setStep("upload");
        setFileKey(""); setFileName(""); setPreview(null);
        setPhoneCol(""); setFirstCol(NONE); setLastCol(NONE); setEmailCol(NONE); setExtras({});
        setCountry(""); setListChoice(NONE); setNewList(""); setStrategy("skip");
        setProgress(null); setError(null); setSubmitting(false);
    }

    function close(next: boolean) {
        if (!next) {
            if (step === "done") onDone();
            reset();
        }
        onOpenChange(next);
    }

    async function onFileUploaded(key: string, name: string) {
        setFileKey(key);
        setFileName(name);
        setLoadingPreview(true);
        setError(null);
        try {
            const res = await previewImportApiV1ContactsImportPreviewGet({ query: { source_key: key } });
            if (res.error || !res.data) {
                setError(detailFromError(res.error, "Could not read the file"));
                return;
            }
            const data = res.data;
            setPreview(data);
            const guess = guessColumns(data.headers);
            setPhoneCol(guess.phone_number ?? "");
            setFirstCol(guess.first_name ?? NONE);
            setLastCol(guess.last_name ?? NONE);
            setEmailCol(guess.email ?? NONE);
            const mapped = new Set(Object.values(guess).filter(Boolean) as string[]);
            const taken: string[] = [];
            const next: Record<string, Extra> = {};
            for (const h of data.headers) {
                if (mapped.has(h)) continue;
                const name = fieldNameFromHeader(h, taken);
                taken.push(name);
                next[h] = { include: true, name };
            }
            setExtras(next);
            setStep("map");
        } catch (e) {
            setError(detailFromError(e, "Could not read the file"));
        } finally {
            setLoadingPreview(false);
        }
    }

    // Standard columns can each be used once; a column already mapped is not an
    // option for another field.
    const usedByStandard = [phoneCol, firstCol, lastCol, emailCol].filter((v) => v && v !== NONE);
    const chosenExtras = Object.entries(extras).filter(([h, e]) => e.include && !usedByStandard.includes(h));
    const extraNames = chosenExtras.map(([, e]) => e.name);
    const extraProblems = chosenExtras.filter(([, e]) => validateFieldName(e.name) !== null);
    const duplicateNames = new Set(extraNames.filter((n, i) => extraNames.indexOf(n) !== i));
    const canStart = Boolean(phoneCol) && (suppression || (extraProblems.length === 0 && duplicateNames.size === 0));

    async function start() {
        setSubmitting(true);
        setError(null);
        try {
            let body: ContactImportResponse | undefined;
            if (suppression) {
                const res = await importSuppressionsApiV1ContactsSuppressionsImportPost({
                    body: { source_key: fileKey, phone_column: phoneCol, country_hint: country.trim() || null },
                });
                if (res.error || !res.data) throw new Error(detailFromError(res.error, "Could not start the import"));
                body = res.data;
            } else {
                let listUuid: string | null = listChoice === NONE ? null : listChoice;
                if (newList.trim()) {
                    const made = await createContactListApiV1ContactsListsPost({ body: { name: newList.trim() } });
                    if (made.error || !made.data) throw new Error(detailFromError(made.error, "Could not create the list"));
                    listUuid = made.data.list_uuid;
                }
                const res = await importContactsApiV1ContactsImportPost({
                    body: {
                        source_key: fileKey,
                        contact_list_uuid: listUuid,
                        dedupe_strategy: strategy,
                        column_mapping: {
                            phone_number: phoneCol,
                            first_name: firstCol === NONE ? null : firstCol,
                            last_name: lastCol === NONE ? null : lastCol,
                            email: emailCol === NONE ? null : emailCol,
                            attributes: Object.fromEntries(chosenExtras.map(([h, e]) => [e.name, h])),
                            country_hint: country.trim() || null,
                        },
                    },
                });
                if (res.error || !res.data) throw new Error(detailFromError(res.error, "Could not start the import"));
                body = res.data;
            }
            setProgress(body);
            setStep("running");
            watch(body.import_uuid, Date.now());
        } catch (e) {
            setError(e instanceof Error ? e.message : "Could not start the import");
        } finally {
            setSubmitting(false);
        }
    }

    function watch(uuid: string, startedAt: number) {
        poll.current = setTimeout(async () => {
            try {
                const res = await getImportApiV1ContactsImportsImportUuidGet({ path: { import_uuid: uuid } });
                if (res.data) {
                    setProgress(res.data);
                    if (res.data.status === "completed" || res.data.status === "failed") {
                        setStep("done");
                        return;
                    }
                }
            } catch {
                /* a missed poll is not a failed import: try again */
            }
            if (Date.now() - startedAt > POLL_LIMIT_MS) {
                setError("This is taking longer than expected. It is still running; check back in a few minutes.");
                setStep("done");
                return;
            }
            watch(uuid, startedAt);
        }, POLL_MS);
    }

    async function downloadRejected() {
        if (!progress) return;
        const res = await getImportErrorReportUrlApiV1ContactsImportsImportUuidErrorReportUrlGet({
            path: { import_uuid: progress.import_uuid },
        });
        if (res.error || !res.data) {
            toast.error(detailFromError(res.error, "Could not get the rejected rows"));
            return;
        }
        window.open(res.data.url, "_blank", "noopener");
    }

    const ColumnSelect = ({ id, label, value, onChange, required = false }: {
        id: string; label: string; value: string; onChange: (v: string) => void; required?: boolean;
    }) => (
        <div className="space-y-1.5">
            <Label htmlFor={id} className="text-xs">{label}{required && " *"}</Label>
            <Select value={value || undefined} onValueChange={onChange}>
                <SelectTrigger id={id}><SelectValue placeholder="Choose a column" /></SelectTrigger>
                <SelectContent>
                    {!required && <SelectItem value={NONE}>Not in the file</SelectItem>}
                    {preview?.headers.map((h) => (
                        <SelectItem key={h} value={h} disabled={usedByStandard.includes(h) && h !== value}>{h}</SelectItem>
                    ))}
                </SelectContent>
            </Select>
        </div>
    );

    return (
        <Dialog open={open} onOpenChange={close}>
            <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-2xl">
                <DialogHeader>
                    <DialogTitle>{suppression ? "Import a do-not-call file" : "Import contacts"}</DialogTitle>
                    <DialogDescription>
                        {step === "upload" && "Upload a CSV with a header row. Up to 10 MB."}
                        {step === "map" && `Say which column is which in ${fileName}.`}
                        {step === "running" && "Importing. You can keep working; this runs in the background."}
                        {step === "done" && (progress?.status === "failed" ? "The import did not complete." : "Finished.")}
                    </DialogDescription>
                </DialogHeader>

                {error && <p className="text-sm text-destructive">{error}</p>}

                {step === "upload" && (
                    <div className="space-y-3">
                        <CsvUploadSelector onFileUploaded={onFileUploaded} selectedFileName={fileName || undefined} />
                        {loadingPreview && (
                            <p className="flex items-center gap-2 text-sm text-muted-foreground">
                                <Loader2 className="h-4 w-4 animate-spin" /> Reading the file…
                            </p>
                        )}
                        {suppression && (
                            <p className="text-xs text-muted-foreground">
                                Every number in the file is added to the do-not-call list. Numbers already on it are left alone.
                            </p>
                        )}
                    </div>
                )}

                {step === "map" && preview && (
                    <div className="space-y-5">
                        <div className="grid gap-4 sm:grid-cols-2">
                            <ColumnSelect id="map-phone" label="Phone number" value={phoneCol} onChange={setPhoneCol} required />
                            {!suppression && <ColumnSelect id="map-first" label="First name" value={firstCol} onChange={setFirstCol} />}
                            {!suppression && <ColumnSelect id="map-last" label="Last name" value={lastCol} onChange={setLastCol} />}
                            {!suppression && <ColumnSelect id="map-email" label="Email" value={emailCol} onChange={setEmailCol} />}
                        </div>

                        <div className="space-y-1.5">
                            <Label htmlFor="map-country" className="text-xs">Country for numbers written without a country code</Label>
                            <Input
                                id="map-country"
                                value={country}
                                maxLength={2}
                                placeholder="e.g. AE"
                                className="w-24 uppercase"
                                onChange={(e) => setCountry(e.target.value.toUpperCase())}
                            />
                            <p className="text-xs text-muted-foreground">
                                Without it, a number like 050 123 4567 cannot be read and the row is rejected. Numbers that start with + never need it.
                            </p>
                        </div>

                        {!suppression && Object.keys(extras).length > 0 && (
                            <div className="space-y-2">
                                <Label className="text-xs">Keep the other columns as custom fields</Label>
                                <p className="text-xs text-muted-foreground">
                                    A custom field can be used in an agent&apos;s prompts, for example {"{{company}}"}.
                                </p>
                                <div className="space-y-2 rounded-md border p-3">
                                    {Object.entries(extras).map(([header, extra]) => {
                                        const taken = usedByStandard.includes(header);
                                        const problem = extra.include && !taken ? validateFieldName(extra.name) : null;
                                        return (
                                            <div key={header} className="flex items-center gap-3">
                                                <Checkbox
                                                    checked={extra.include && !taken}
                                                    disabled={taken}
                                                    onCheckedChange={(v) => setExtras((p) => ({ ...p, [header]: { ...p[header], include: v === true } }))}
                                                    aria-label={`Keep ${header}`}
                                                />
                                                <span className="w-40 shrink-0 truncate text-sm" title={header}>{header}</span>
                                                <span className="text-muted-foreground">→</span>
                                                <Input
                                                    value={extra.name}
                                                    disabled={!extra.include || taken}
                                                    aria-label={`Field name for ${header}`}
                                                    className="h-8 flex-1"
                                                    onChange={(e) => setExtras((p) => ({ ...p, [header]: { ...p[header], name: e.target.value } }))}
                                                />
                                                {problem && <span className="text-xs text-destructive">{problem}</span>}
                                            </div>
                                        );
                                    })}
                                    {duplicateNames.size > 0 && (
                                        <p className="text-xs text-destructive">Two columns have the same field name.</p>
                                    )}
                                </div>
                            </div>
                        )}

                        {!suppression && (
                            <div className="grid gap-4 sm:grid-cols-2">
                                <div className="space-y-1.5">
                                    <Label className="text-xs">Add them to a list</Label>
                                    <Select value={listChoice} onValueChange={setListChoice} disabled={Boolean(newList.trim())}>
                                        <SelectTrigger><SelectValue /></SelectTrigger>
                                        <SelectContent>
                                            <SelectItem value={NONE}>No list</SelectItem>
                                            {lists.map((l) => (
                                                <SelectItem key={l.list_uuid} value={l.list_uuid}>{l.name} ({l.contact_count})</SelectItem>
                                            ))}
                                        </SelectContent>
                                    </Select>
                                </div>
                                <div className="space-y-1.5">
                                    <Label htmlFor="map-newlist" className="text-xs">…or a new list</Label>
                                    <Input id="map-newlist" value={newList} placeholder="List name" onChange={(e) => setNewList(e.target.value)} />
                                </div>
                                <div className="space-y-1.5 sm:col-span-2">
                                    <Label className="text-xs">If a contact already exists</Label>
                                    <Select value={strategy} onValueChange={(v) => setStrategy(v as "skip" | "update")}>
                                        <SelectTrigger className="max-w-sm"><SelectValue /></SelectTrigger>
                                        <SelectContent>
                                            <SelectItem value="skip">Leave them as they are</SelectItem>
                                            <SelectItem value="update">Fill in what is new and update custom fields</SelectItem>
                                        </SelectContent>
                                    </Select>
                                    <p className="text-xs text-muted-foreground">
                                        The same person written two ways, like +1 (415) 555-1234 and +14155551234, is always one contact.
                                    </p>
                                </div>
                            </div>
                        )}

                        <div>
                            <Label className="text-xs">First rows of the file</Label>
                            <div className="mt-1.5 overflow-x-auto rounded-md border">
                                <table className="w-full text-xs">
                                    <thead className="bg-muted/50">
                                        <tr>{preview.headers.map((h) => <th key={h} className="px-2 py-1.5 text-left font-medium">{h}</th>)}</tr>
                                    </thead>
                                    <tbody>
                                        {preview.rows.map((r, i) => (
                                            <tr key={i} className="border-t">
                                                {preview.headers.map((_, j) => <td key={j} className="whitespace-nowrap px-2 py-1">{r[j]}</td>)}
                                            </tr>
                                        ))}
                                    </tbody>
                                </table>
                            </div>
                        </div>
                    </div>
                )}

                {(step === "running" || step === "done") && progress && (
                    <div className="space-y-3 py-2">
                        <div className="flex items-center gap-2">
                            {progress.status === "failed" ? (
                                <XCircle className="h-5 w-5 text-destructive" />
                            ) : progress.status === "completed" ? (
                                <CheckCircle2 className="h-5 w-5 text-primary" />
                            ) : (
                                <Loader2 className="h-5 w-5 animate-spin" />
                            )}
                            <span className="font-medium">
                                {progress.status === "failed"
                                    ? "Import failed"
                                    : progress.status === "completed"
                                      ? "Import complete"
                                      : "Importing…"}
                            </span>
                        </div>
                        {progress.status === "failed" && progress.processing_error && (
                            <p className="text-sm text-destructive">{progress.processing_error}</p>
                        )}
                        <p className="text-sm tabular-nums text-muted-foreground">{importSummary(progress)}</p>
                        {progress.status === "completed" && progress.has_error_report && (
                            <Button variant="outline" size="sm" onClick={downloadRejected}>
                                <Download /> Download the {(progress.invalid_count ?? 0).toLocaleString()} rejected rows
                            </Button>
                        )}
                    </div>
                )}

                <DialogFooter>
                    {step === "map" && (
                        <>
                            <Button variant="ghost" onClick={reset}>Choose a different file</Button>
                            <Button onClick={start} disabled={!canStart || submitting}>
                                {submitting ? "Starting…" : suppression ? "Add to do-not-call list" : "Import"}
                            </Button>
                        </>
                    )}
                    {(step === "done" || step === "upload") && (
                        <Button variant={step === "done" ? "default" : "ghost"} onClick={() => close(false)}>
                            {step === "done" ? "Done" : "Cancel"}
                        </Button>
                    )}
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}
