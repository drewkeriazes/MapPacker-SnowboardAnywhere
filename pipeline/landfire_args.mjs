// The positional arguments of fetch_landfire.mjs, after --raw and --force are taken out (BUG-111).
// <slug> [<email>] [layer]: the email is LANDFIRE_EMAIL, else the argument after <slug> when it has an "@"
// (a product or layer name never does), so the layer argument is the same with or without the email argument.
export function parseArgs(argv, env = {}) {
  const [slug, a, b] = argv;
  const given = a !== undefined && a.includes('@');
  const email = given ? a : env.LANDFIRE_EMAIL || null;
  const layerArg = (given ? b : a) ?? 'EVT';
  return { slug, email, layerArg };
}
