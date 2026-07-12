export interface IcsEventInput {
  uid: string;
  date: string; // YYYY-MM-DD
  title: string;
  url?: string;
}

function escapeIcsText(s: string): string {
  return s.replace(/\\/g, '\\\\').replace(/([,;])/g, '\\$1');
}

/** 発売日1件分の.icsをdata URIとして生成する（終日イベント）。ビルド時に静的計算するためJS不要。 */
export function buildIcsDataUri({ uid, date, title, url }: IcsEventInput): string {
  const dtStart = date.replace(/-/g, '');
  const endDate = new Date(`${date}T00:00:00`);
  endDate.setDate(endDate.getDate() + 1);
  const dtEnd = endDate.toISOString().slice(0, 10).replace(/-/g, '');

  const lines = [
    'BEGIN:VCALENDAR',
    'VERSION:2.0',
    'PRODID:-//gacha-calendar//JP',
    'CALSCALE:GREGORIAN',
    'BEGIN:VEVENT',
    `UID:${uid}@gacha-calendar-20p.pages.dev`,
    `DTSTART;VALUE=DATE:${dtStart}`,
    `DTEND;VALUE=DATE:${dtEnd}`,
    `SUMMARY:${escapeIcsText(title)} 発売`,
    url ? `URL:${url}` : '',
    'END:VEVENT',
    'END:VCALENDAR',
  ].filter(Boolean);

  return `data:text/calendar;charset=utf-8,${encodeURIComponent(lines.join('\r\n'))}`;
}
