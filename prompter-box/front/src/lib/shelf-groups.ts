// The Stage's choreography pick and the Foley Booth's reel pick read the same
// two shelves. As GroupSelect groups: the "none" entry rides headerless on top
// (id '' — a pick must stay clearable), then the stage takes, then footage.
// `label` keeps the shelf prefix for the closed trigger; `name` is what the
// list shows under its shelf's header.

export interface ShelfOption {
    id: string;
    label: string;
    name: string;
}

export interface ShelfGroup {
    text: string;
    header?: boolean;
    options: ShelfOption[];
}

const shelfRun = (shelf: 'stage' | 'footage', names: string[]): ShelfOption[] =>
    names.map(name => ({id: `${shelf}:${name}`, label: `${shelf} · ${name}`, name}));

export const shelfGroups = (noneLabel: string, shelves: {stage: string[]; footage: string[]}): ShelfGroup[] => [
    {text: '', header: false, options: [{id: '', label: noneLabel, name: noneLabel}]},
    {text: 'stage takes', options: shelfRun('stage', shelves.stage)},
    {text: 'footage', options: shelfRun('footage', shelves.footage)},
];
