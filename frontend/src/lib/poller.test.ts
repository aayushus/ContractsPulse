import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { createAdaptivePoller } from './poller';

describe('createAdaptivePoller', () => {
    let mockHidden = false;

    beforeEach(() => {
        vi.useFakeTimers();
        mockHidden = false;

        Object.defineProperty(document, 'hidden', {
            configurable: true,
            get: () => mockHidden
        });
    });

    afterEach(() => {
        vi.useRealTimers();
        vi.clearAllMocks();
    });

    it('runs immediately by default', async () => {
        const fn = vi.fn().mockResolvedValue(undefined);
        const poller = createAdaptivePoller({
            fn,
            isActive: () => true
        });

        poller.start();
        expect(fn).toHaveBeenCalledTimes(1);
        poller.stop();
    });

    it('does not run immediately if runImmediately is false', async () => {
        const fn = vi.fn().mockResolvedValue(undefined);
        const poller = createAdaptivePoller({
            fn,
            isActive: () => true,
            runImmediately: false,
            activeMs: 1000
        });

        poller.start();
        expect(fn).toHaveBeenCalledTimes(0);

        await vi.advanceTimersByTimeAsync(1000);
        expect(fn).toHaveBeenCalledTimes(1);

        poller.stop();
    });

    it('polls at activeMs when isActive is true', async () => {
        const fn = vi.fn().mockResolvedValue(undefined);
        const poller = createAdaptivePoller({
            fn,
            isActive: () => true,
            activeMs: 1000,
            runImmediately: false
        });

        poller.start();

        await vi.advanceTimersByTimeAsync(1000);
        expect(fn).toHaveBeenCalledTimes(1);

        await vi.advanceTimersByTimeAsync(1000);
        expect(fn).toHaveBeenCalledTimes(2);

        poller.stop();
    });

    it('polls at idleMs when isActive is false', async () => {
        const fn = vi.fn().mockResolvedValue(undefined);
        const poller = createAdaptivePoller({
            fn,
            isActive: () => false,
            idleMs: 5000,
            runImmediately: false
        });

        poller.start();

        await vi.advanceTimersByTimeAsync(1000);
        expect(fn).toHaveBeenCalledTimes(0);

        await vi.advanceTimersByTimeAsync(4000); // total 5000
        expect(fn).toHaveBeenCalledTimes(1);

        poller.stop();
    });

    it('changes polling rate based on isActive', async () => {
        let active = true;
        const fn = vi.fn().mockImplementation(() => {
            return Promise.resolve();
        });

        const poller = createAdaptivePoller({
            fn,
            isActive: () => active,
            activeMs: 1000,
            idleMs: 5000,
            runImmediately: false
        });

        poller.start();

        await vi.advanceTimersByTimeAsync(1000);
        expect(fn).toHaveBeenCalledTimes(1);

        active = false;

        await vi.advanceTimersByTimeAsync(1000);
        expect(fn).toHaveBeenCalledTimes(2);

        await vi.advanceTimersByTimeAsync(1000);
        expect(fn).toHaveBeenCalledTimes(2);

        await vi.advanceTimersByTimeAsync(4000);
        expect(fn).toHaveBeenCalledTimes(3);

        poller.stop();
    });

    it('pauses polling when document is hidden', async () => {
        const fn = vi.fn().mockResolvedValue(undefined);
        const poller = createAdaptivePoller({
            fn,
            isActive: () => true,
            activeMs: 1000,
            runImmediately: false
        });

        poller.start();

        mockHidden = true; // document hidden

        await vi.advanceTimersByTimeAsync(1000);
        expect(fn).toHaveBeenCalledTimes(0);

        await vi.advanceTimersByTimeAsync(5000);
        expect(fn).toHaveBeenCalledTimes(0);

        poller.stop();
    });

    it('resumes polling immediately when document becomes visible', async () => {
        const fn = vi.fn().mockResolvedValue(undefined);
        const poller = createAdaptivePoller({
            fn,
            isActive: () => true,
            activeMs: 1000,
            runImmediately: false
        });

        poller.start();

        mockHidden = true;

        await vi.advanceTimersByTimeAsync(1000);
        expect(fn).toHaveBeenCalledTimes(0);

        // Simulate visibility change
        mockHidden = false;
        document.dispatchEvent(new Event('visibilitychange'));

        await Promise.resolve();
        await Promise.resolve();
        await Promise.resolve();

        expect(fn).toHaveBeenCalledTimes(1);

        // Then continue polling at activeMs
        await vi.advanceTimersByTimeAsync(1000);
        expect(fn).toHaveBeenCalledTimes(2);

        poller.stop();
    });

    it('does not overlap runs if fn takes longer than delay', async () => {
        let resolveFn: () => void;
        const promise = new Promise<void>(r => { resolveFn = r; });

        const fn = vi.fn().mockReturnValue(promise);
        const poller = createAdaptivePoller({
            fn,
            isActive: () => true,
            activeMs: 1000,
            runImmediately: true
        });

        poller.start();

        expect(fn).toHaveBeenCalledTimes(1);

        // advance timer while fn is still running
        await vi.advanceTimersByTimeAsync(1000);
        expect(fn).toHaveBeenCalledTimes(1);

        await vi.advanceTimersByTimeAsync(1000);
        expect(fn).toHaveBeenCalledTimes(1);

        // resolve the function
        resolveFn!();
        await Promise.resolve();
        await Promise.resolve();
        await Promise.resolve();

        // advance timer to trigger next schedule
        await vi.advanceTimersByTimeAsync(1000);
        expect(fn).toHaveBeenCalledTimes(2);

        poller.stop();
    });

    it('stops polling when stop() is called', async () => {
        const fn = vi.fn().mockResolvedValue(undefined);
        const poller = createAdaptivePoller({
            fn,
            isActive: () => true,
            activeMs: 1000,
            runImmediately: false
        });

        poller.start();

        await vi.advanceTimersByTimeAsync(1000);
        expect(fn).toHaveBeenCalledTimes(1);

        poller.stop();

        await vi.advanceTimersByTimeAsync(1000);
        expect(fn).toHaveBeenCalledTimes(1);
    });

    it('ignores start() if already started', async () => {
        const fn = vi.fn().mockResolvedValue(undefined);
        const poller = createAdaptivePoller({
            fn,
            isActive: () => true,
            activeMs: 1000,
            runImmediately: true
        });

        poller.start();
        poller.start(); // second call

        expect(fn).toHaveBeenCalledTimes(1);

        poller.stop();
    });
});
