// Static endpoint: the global event search index, emitted as
// /events/search-index.json at build time. The Story Events index page fetches
// it lazily on the first search keystroke so the HTML stays small.
//
// This is the ONE index across all five event pages (story events + the four
// dedicated pages: expeditions, ruins, harvest, study) so a single search box
// finds any event and links straight to its card wherever it renders.
// Entry shape: { i: id, n: name, g: group label, h: href (relative to base) }.
// Titles only — story body prose is deliberately not shipped (in-game discovery).
import search from '../../data/event-search.json';

export function GET() {
  return new Response(JSON.stringify(search), {
    headers: { 'Content-Type': 'application/json' },
  });
}
