/**
 * Topic selection over the taxonomy tree (domain › subjects › ...), with free choice at every level.
 *
 * A stored code covers itself and everything below it. Unchecking a subject inside a covered domain keeps the
 * rest of that domain; checking every subject of a domain stores the domain itself, so subjects added to
 * the taxonomy later are followed too.
 */
export type TopicNode = { code: string; parent_id?: string | null };
export type TopicTree = { parent: Map<string, string | null>; children: Map<string, string[]> };
export type Coverage = 'all' | 'some' | 'none';

export function buildTopicTree(topics: TopicNode[]): TopicTree {
  const parent = new Map<string, string | null>();
  const children = new Map<string, string[]>();
  for (const topic of topics) {
    parent.set(topic.code, topic.parent_id || null);
    if (topic.parent_id) children.set(topic.parent_id, [...(children.get(topic.parent_id) || []), topic.code]);
  }
  return { parent, children };
}

function ancestors(code: string, tree: TopicTree) {
  const chain: string[] = [];
  for (let current = tree.parent.get(code); current; current = tree.parent.get(current)) chain.unshift(current);
  return chain;
}

function descendants(code: string, tree: TopicTree): string[] {
  return (tree.children.get(code) || []).flatMap(child => [child, ...descendants(child, tree)]);
}

export function isCovered(selection: string[], code: string, tree: TopicTree) {
  return selection.includes(code) || ancestors(code, tree).some(ancestor => selection.includes(ancestor));
}

/** 'all' when the topic is followed, 'some' when only part of what is below it is. */
export function coverage(selection: string[], code: string, tree: TopicTree): Coverage {
  if (isCovered(selection, code, tree)) return 'all';
  return descendants(code, tree).some(child => selection.includes(child)) ? 'some' : 'none';
}

export function toggleTopic(selection: string[], code: string, tree: TopicTree): string[] {
  const next = new Set(selection);
  if (isCovered(selection, code, tree)) {
    const path = [...ancestors(code, tree), code];
    const owner = path.findIndex(node => next.has(node));
    next.delete(path[owner]);
    // Re-add every sibling along the way down, so only `code` (and what is below it) stops being followed.
    for (let index = owner; index < path.length - 1; index++) {
      for (const child of tree.children.get(path[index]) || []) if (child !== path[index + 1]) next.add(child);
    }
  } else {
    next.add(code);
    for (const child of descendants(code, tree)) next.delete(child);
    // A domain whose subjects are all checked becomes the domain itself.
    for (let parent = tree.parent.get(code); parent; parent = tree.parent.get(parent)) {
      const siblings = tree.children.get(parent) || [];
      if (!siblings.length || !siblings.every(child => next.has(child))) break;
      siblings.forEach(child => next.delete(child));
      next.add(parent);
    }
  }
  // Keep the user's order for what stays, new codes at the end.
  return [...selection.filter(item => next.has(item)), ...[...next].filter(item => !selection.includes(item))];
}
