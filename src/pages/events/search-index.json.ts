// Static endpoint: the lightweight Story Events search index, emitted as
// /events/search-index.json at build time. The events index page fetches it
// lazily on the first search keystroke so the HTML stays small.
// Entry shape: { i: event id, n: name, s: category part slug, g: group label,
//                t?: first 140 chars of body text }.
import search from '../../data/story-events/search.json';

export function GET() {
  return new Response(JSON.stringify(search), {
    headers: { 'Content-Type': 'application/json' },
  });
}
