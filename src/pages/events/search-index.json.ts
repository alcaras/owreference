// Static endpoint: the lightweight Story Events search index, emitted as
// /events/search-index.json at build time. The events index page fetches it
// lazily on the first search keystroke so the HTML stays small.
// Entry shape: { i: event id, n: name, s: category part slug, g: group label }.
// Titles only — story body prose is deliberately not shipped (in-game discovery).
import search from '../../data/story-events/search.json';

export function GET() {
  return new Response(JSON.stringify(search), {
    headers: { 'Content-Type': 'application/json' },
  });
}
