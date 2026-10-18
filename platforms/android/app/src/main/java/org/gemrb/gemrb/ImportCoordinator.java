package org.gemrb.gemrb;

import java.io.IOException;
import java.util.concurrent.atomic.AtomicBoolean;

/** Serializes cancellation with the durable registry commit boundary. */
final class ImportCoordinator {
    interface Commit { void run() throws IOException; }
    private final AtomicBoolean cancelled = new AtomicBoolean();
    private boolean committing;
    private boolean committed;
    private boolean finished;

    AtomicBoolean cancellation() { return cancelled; }

    synchronized boolean cancel() {
        if (committing || committed || finished) return false;
        cancelled.set(true);
        return true;
    }

    boolean commit(Commit action) throws IOException {
        synchronized (this) {
            if (cancelled.get() || finished || committing || committed) return false;
            committing = true;
        }
        try {
            action.run();
            synchronized (this) { committed = true; }
            return true;
        } finally {
            synchronized (this) { committing = false; }
        }
    }

    synchronized boolean isCommitted() { return committed; }
    synchronized boolean finish() {
        if (finished) return false;
        finished = true;
        return true;
    }
}
