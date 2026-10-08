export interface RoomJourney {
    title: string;
    purpose: string;
    steps: {label: string; target: string}[];
}

// Each room owns a different job. The shared rail only guides the hand;
// it never starts a machine, gates editing, or invents progress.
export const ROOM_JOURNEYS: Record<string, RoomJourney> = {
    forge: {title: 'Give the idea its lines', purpose: 'Draft a cue, make it yours, then send it to the room that will perform it.', steps: [
        {label: 'Brief', target: '#idea'}, {label: 'Reference', target: '#forge-thumbs'}, {label: 'Choose a cue', target: '#cards'},
    ]},
    face: {title: 'Give the character another take', purpose: 'Change one thing, compare the character, and choose where the next version begins.', steps: [
        {label: 'Character', target: '#face-source'}, {label: 'Change brief', target: '#face-prompt'}, {label: 'Paint', target: '#face-go'},
        {label: 'Compare', target: '#face-compare'}, {label: 'Choose a version', target: '#face-revisions'},
    ]},
    stage: {title: 'Put the character in motion', purpose: 'Choose the performance first. The playbill follows the job.', steps: [
        {label: 'Task', target: '#stage-task'}, {label: 'Lead', target: '#thumbs'}, {label: 'Motion brief', target: '#stage-prompt'}, {label: 'Review the take', target: '#stage-result'},
    ]},
    foley: {title: 'Give the take its sound', purpose: 'Make a sound on its own, or score the motion already on the reel.', steps: [
        {label: 'Task / reel', target: '#foley-task'}, {label: 'Sound brief', target: '#foley-prompt'}, {label: 'Record', target: '#foley-go'}, {label: 'Audition / export', target: '#foley-result'},
    ]},
    kiln: {title: 'Fire a prop worth keeping', purpose: 'Brief the prop, dress the firing, then inspect it before passing judgment.', steps: [
        {label: 'Subject', target: '#kiln-subject'}, {label: 'Settings', target: '.kiln-settings'}, {label: 'Fire', target: '#kiln-go'}, {label: 'Inspect / review', target: '#kiln-result'},
    ]},
    rack: {title: 'Give each firing a verdict', purpose: 'Inspect the shape and its checks. Approve, refire, or discard the candidate.', steps: [
        {label: 'Choose candidate', target: '#rack-grid'}, {label: 'Inspect', target: '#rack-view'}, {label: 'Verdict', target: '#rack-view'},
    ]},
    shelf: {title: 'Take an approved prop home', purpose: 'Find the piece, turn it in the light, then take its mesh and painting together.', steps: [
        {label: 'Find', target: '#shelf-search'}, {label: 'Inspect', target: '#shelf-view'}, {label: 'Export', target: '#shelf-export'},
    ]},
    nightshift: {title: 'Brief the shift before it starts', purpose: 'Order variants of one prop or a list of different props. Every result still needs your verdict.', steps: [
        {label: 'Orders', target: '#shift-subject'}, {label: 'Call sheet', target: '#shift-rows'}, {label: 'Run', target: '#shift-start'}, {label: 'Review candidates', target: '#shift-review'},
    ]},
    archive: {title: 'Put a proven take back to work', purpose: 'Find it, inspect it, then refine, reuse, pin, or take it home.', steps: [
        {label: 'Find', target: '#arch-search'}, {label: 'Inspect', target: '.bench'}, {label: 'Reuse / export', target: '.bench'},
    ]},
    'house-stage': {title: 'The advanced motion desk', purpose: 'The native Wan2GP controls, with a door back to your finished takes.', steps: [
        {label: 'Open the machine', target: '#house-stage-open'}, {label: 'Native controls', target: '#house-stage-frame'}, {label: 'Collect takes', target: '#house-stage-collect'},
    ]},
    'house-face': {title: 'The advanced painting desk', purpose: 'The native ComfyUI graph, with a door back to your finished paintings.', steps: [
        {label: 'Open the machine', target: '#house-face-open'}, {label: 'Native graph', target: '#house-face-frame'}, {label: 'Collect paintings', target: '#house-face-collect'},
    ]},
};
