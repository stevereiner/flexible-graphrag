import { DOCUMENT } from '@angular/common';
import { Injectable, inject } from '@angular/core';
import { BehaviorSubject } from 'rxjs';

/**
 * Dark / light mode for an app built on this library: a ``dark-theme`` or ``light-theme`` class on
 * ``<body>``, which the library's components and its ``styles/fg-theme.scss`` style. The choice is
 * kept per browser (localStorage); before there is one, the browser's colour scheme. A host with a
 * theme of its own (ACA) doesn't use this.
 */
@Injectable({ providedIn: 'root' })
export class FlexibleGraphragThemeService {
  /** The storage key (the standalone Angular app's, so its users keep their choice). */
  static readonly STORAGE_KEY = 'angular-theme-mode';

  private readonly doc = inject(DOCUMENT);
  private readonly dark$ = new BehaviorSubject<boolean>(this.initial());
  readonly darkChanges = this.dark$.asObservable();

  constructor() {
    this.apply(this.dark$.value);
  }

  get dark(): boolean {
    return this.dark$.value;
  }

  setDark(dark: boolean): void {
    try {
      localStorage.setItem(FlexibleGraphragThemeService.STORAGE_KEY, dark ? 'dark' : 'light');
    } catch {
      // storage blocked: the choice lasts for this page only
    }
    this.apply(dark);
    this.dark$.next(dark);
  }

  toggle(): void {
    this.setDark(!this.dark);
  }

  private initial(): boolean {
    try {
      const saved = localStorage.getItem(FlexibleGraphragThemeService.STORAGE_KEY);
      if (saved === 'dark' || saved === 'light') {
        return saved === 'dark';
      }
    } catch {
      // storage blocked
    }
    return !!this.doc.defaultView?.matchMedia?.('(prefers-color-scheme: dark)').matches;
  }

  private apply(dark: boolean): void {
    const body = this.doc.body;
    body.classList.toggle('dark-theme', dark);
    body.classList.toggle('light-theme', !dark);
  }
}
