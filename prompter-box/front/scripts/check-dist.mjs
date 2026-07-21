// The dist-drift guard (#00063 §1A): the committed static/booth bundle must
// match a fresh build of the current source — a stale committed bundle is a
// lie the repo tells the bench. Run via `npm run check:dist`, which rebuilds
// first; any resulting git diff (or untracked file) under static/booth fails.
import {execSync} from 'node:child_process';

const out = execSync('git status --porcelain -- ../static/booth', {encoding: 'utf8'}).trim();
if (out) {
    console.error(`dist drift — static/booth does not match a fresh build:\n${out}\n` +
        'Rebuild and commit the bundle alongside the source change.');
    process.exit(1);
}
console.log('static/booth matches a fresh build — no drift.');
