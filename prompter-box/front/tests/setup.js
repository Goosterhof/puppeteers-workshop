// jsdom carries no dialog methods and no scrollIntoView — shim just enough
// for the break-pit and the spotlight scroll.
HTMLDialogElement.prototype.showModal ??= function () {
    this.open = true;
};
HTMLDialogElement.prototype.close ??= function () {
    this.open = false;
    this.dispatchEvent(new Event('close'));
};
Element.prototype.scrollIntoView ??= function () {};

// jsdom carries no matchMedia — the booth reads it for the reduced-motion
// gates. `globalThis.__reducedMotion` lets a spec flip the preference.
globalThis.__reducedMotion = false;
window.matchMedia = query => ({
    media: query,
    get matches() {
        return query.includes('prefers-reduced-motion') ? globalThis.__reducedMotion : false;
    },
    addEventListener() {},
    removeEventListener() {},
});
