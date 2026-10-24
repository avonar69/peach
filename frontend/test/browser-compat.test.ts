import { describe, expect, it } from 'vitest';
import { installBrowserCompat, randomUUID } from '../src/browser-compat';

describe('HTTP browser UUID support', () => {
  it('generates distinct RFC 4122 version 4 identifiers', () => {
    const values = new Set(Array.from({ length: 1000 }, randomUUID));
    expect(values.size).toBe(1000);
    for (const value of values) expect(value).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/);
  });
  it('installs the fallback when randomUUID is unavailable and preserves native implementations', () => {
    const native = crypto.randomUUID;
    Object.defineProperty(crypto, 'randomUUID', { value: undefined, configurable: true });
    try {
      installBrowserCompat();
      expect(crypto.randomUUID()).toMatch(/^[0-9a-f-]{36}$/);
      const installed = crypto.randomUUID;
      installBrowserCompat();
      expect(crypto.randomUUID).toBe(installed);
    } finally { Object.defineProperty(crypto, 'randomUUID', { value: native, configurable: true }); }
  });
});
