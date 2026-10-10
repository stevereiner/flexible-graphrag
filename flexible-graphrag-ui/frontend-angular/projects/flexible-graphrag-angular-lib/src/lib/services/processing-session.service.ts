import { Injectable } from '@angular/core';

/**
 * Keeps the Processing tab's state while the tab itself is destroyed.
 *
 * In the standalone apps the four tabs live in one component that is never torn down, so the
 * tab keeps its run, checks and messages when you switch tabs. In an ACA host the whole page
 * is a route: navigating elsewhere in ACA destroys it, and coming back used to show an empty
 * tab while the backend job carried on unseen. The tab saves into ``tab`` when it is destroyed
 * and takes it back when it is created for the same selection; a host saves its configured
 * source into ``hostSelection`` so it can come back without the selection being handed over
 * again (ACA's navbar link carries none).
 */
@Injectable({ providedIn: 'root' })
export class ProcessingSessionService {
  /** The Processing tab's state, with ``key`` naming the selection it belongs to. */
  tab: ({ key: string } & Record<string, any>) | null = null;
  /** The host page's last configured source and tab, for a host whose page is a route. */
  hostSelection: Record<string, any> | null = null;
  /**
   * The search and chat tabs' questions, results and answers, kept the same way -- opening a
   * result's document in ACA's viewer leaves the page, and closing the viewer comes back to it.
   * ``owner`` is the signed-in user's request headers (their ticket in ACA): ACA signs out
   * without reloading, so another user must not get the previous one's answers back.
   */
  searchTab: ({ owner: string } & Record<string, any>) | null = null;
  chatTab: ({ owner: string; scopeKey: string } & Record<string, any>) | null = null;
}
