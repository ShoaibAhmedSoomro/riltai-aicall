/** "4:07" for a call 4 minutes 7 seconds in, "1:02:09" past the hour, "0:00" if the
 *  clock on this machine is behind the server's. */
export function formatElapsed(startedAt: string | Date, now: number = Date.now()): string {
    const start = typeof startedAt === 'string' ? new Date(startedAt).getTime() : startedAt.getTime();
    if (Number.isNaN(start)) return '–';
    const total = Math.max(0, Math.floor((now - start) / 1000));
    const h = Math.floor(total / 3600);
    const m = Math.floor((total % 3600) / 60);
    const s = total % 60;
    const mm = h > 0 ? String(m).padStart(2, '0') : String(m);
    return `${h > 0 ? `${h}:` : ''}${mm}:${String(s).padStart(2, '0')}`;
}
