export type DateRange = { start: string; end: string };

// New imports extend the automatic full range, never a deliberately narrowed view.
export function refreshedRange(current: DateRange, previous: DateRange | null, next: DateRange): DateRange {
  if (!previous || (current.start === previous.start && current.end === previous.end)) return next;
  return current;
}
