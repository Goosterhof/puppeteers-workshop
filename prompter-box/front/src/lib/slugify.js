// The packer's naming law — lowercase letters, digits, and dashes only,
// 48 characters, never empty (the old front's slugify).
export const slugify = text => (text || '').toLowerCase()
    .replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 48) || 'prop';
