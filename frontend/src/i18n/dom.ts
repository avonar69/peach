/** 命令式界面、HTML 回执及门户弹层共用的呈现边界。 */
import { translate } from './index';

const ATTRIBUTES = ['title', 'aria-label', 'aria-description', 'placeholder', 'alt', 'label', 'data-tip', 'data-tooltip'];
const PRESERVE = 'script,style,textarea,code,pre,[contenteditable]:not([contenteditable="false"]),[data-i18n-ignore],[data-detail-title],[data-item-title],[data-card-title],[data-entity-name],[data-creator-name],[data-middle-truncate]';
export function localizeDom(root: Node): void {
  const update = (node: Node) => {
    const element = node.nodeType === Node.ELEMENT_NODE ? node as Element : node.parentElement;
    if (!element || element.closest(PRESERVE)) return;
    if (node.nodeType === Node.TEXT_NODE && node.nodeValue) {
      const translated = translate(node.nodeValue);
      if (translated !== node.nodeValue) node.nodeValue = translated;
    } else if (node.nodeType === Node.ELEMENT_NODE) {
      if (element.tagName === 'OPTION' && !element.hasAttribute('value')) {
        element.setAttribute('value', element.textContent || '');
      }
      for (const attribute of ATTRIBUTES) {
        const original = element.getAttribute(attribute);
        if (original) {
          const translated = translate(original);
          if (translated !== original) element.setAttribute(attribute, translated);
        }
      }
    }
  };
  update(root);
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT | NodeFilter.SHOW_TEXT, {
    acceptNode: (node) => node instanceof Element && node.matches(PRESERVE) ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_ACCEPT,
  });
  while (walker.nextNode()) update(walker.currentNode);
}

export function installDomLocalization(root: Node = document.documentElement): () => void {
  localizeDom(root);
  const title = document.querySelector('title');
  if (title) localizeDom(title);
  const observer = new MutationObserver((records) => {
    const changed = new Set<Node>();
    for (const record of records) {
      if (record.type === 'childList') record.addedNodes.forEach(node => changed.add(node));
      else changed.add(record.target);
    }
    for (const node of changed) if (node.isConnected) localizeDom(node);
  });
  observer.observe(root, { childList: true, subtree: true, characterData: true, attributes: true, attributeFilter: ATTRIBUTES });
  if (title && !root.contains(title)) observer.observe(title, { childList: true, subtree: true, characterData: true });
  return () => observer.disconnect();
}
