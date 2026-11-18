import { Injectable, inject } from '@angular/core';
import { HttpEvent, HttpHandler, HttpInterceptor, HttpRequest } from '@angular/common/http';
import { Observable } from 'rxjs';
import {
  FlexibleGraphragConfigService, desktopInvoke, isDesktopApp, setDesktopInvoke, setDesktopRemoteBackend,
} from '@flexible-graphrag/angular-ui';

const isLocalUrl = (url: string): boolean => {
  try {
    return ['localhost', '127.0.0.1', '[::1]', '::1'].includes(new URL(url).hostname);
  } catch {
    return true;
  }
};

/** desktop/src-tauri/src/backend.rs `backend_info` */
interface BackendInfo {
  url: string | null;
  token: string | null;
}

/**
 * Where the backend is and the API token it wants (its API_TOKEN, sent as X-API-Token), in the
 * desktop app (flexible-graphrag-ui/desktop). In a browser nothing changes: requests stay relative
 * (/api, through the dev server's or nginx's proxy) and carry no token.
 *
 * - The URL and token come from the app (`backend_info`). The library's API URL becomes the
 *   backend's own (setApiUrl), for every request and the sign-in popups, built or under
 *   `ng serve` (whose /api proxy is then not used, so the UI talks to the backend the app chose).
 */
@Injectable({ providedIn: 'root' })
export class DesktopConnection {
  private readonly fgConfig = inject(FlexibleGraphragConfigService);
  token: string | null = null;

  async install(): Promise<void> {
    if (!isDesktopApp()) return;
    try {
      // the desktop commands through @tauri-apps/api (loaded only here, in the desktop app)
      const { invoke } = await import('@tauri-apps/api/core');
      setDesktopInvoke((command, args) => invoke(command, args));
    } catch (e) {
      console.warn('Desktop app: @tauri-apps/api unavailable, using the Tauri global', e);
    }
    try {
      const info = await desktopInvoke<BackendInfo>('backend_info');
      this.token = info.token || null;
      setDesktopRemoteBackend(!!info.url && !isLocalUrl(info.url));
      // the backend the app chose, called directly, under ng serve too: its /api proxy
      // (VITE_API_PROXY_TARGET) may point at another backend than the one the app uses
      if (info.url) this.fgConfig.setApiUrl(`${info.url.replace(/\/+$/, '')}/api`);
    } catch (e) {
      console.warn('Desktop app: backend_info unavailable', e);
    }
  }
}

/** APP_INITIALIZER: backend URL + API token before the first request. */
export function installDesktopConnection(connection: DesktopConnection): () => Promise<void> {
  return () => connection.install();
}

/** Adds the desktop app's API token to requests to the backend (desktop app only). */
@Injectable()
export class DesktopTokenInterceptor implements HttpInterceptor {
  private readonly connection = inject(DesktopConnection);
  private readonly fgConfig = inject(FlexibleGraphragConfigService);

  intercept(req: HttpRequest<unknown>, next: HttpHandler): Observable<HttpEvent<unknown>> {
    const token = this.connection.token;
    if (token && req.url.startsWith(this.fgConfig.apiUrl)) {
      req = req.clone({ setHeaders: { 'X-API-Token': token } });
    }
    return next.handle(req);
  }
}
