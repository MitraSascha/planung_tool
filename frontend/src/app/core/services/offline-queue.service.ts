import { Injectable, computed, signal } from '@angular/core';

/**
 * Offline-Submit-Queue mit IndexedDB als Storage.
 *
 * Pro Eintrag wird gespeichert: URL, HTTP-Methode, Body, Bearer-Token,
 * Content-Type, Zeitstempel + eine kurze Beschreibung (für die UI).
 * Sobald der Browser wieder Online ist, ruft der `SyncService` die
 * `flush()`-Methode auf und sendet alle Einträge nacheinander an das
 * Backend. Erfolgreich gesendete Einträge werden aus der Queue entfernt.
 *
 * Wir verzichten bewusst auf eine externe Lib (`idb`) und nutzen die
 * native IndexedDB-API — kein zusätzlicher Bundle-Overhead.
 */

const DB_NAME = 'mitra-offline-queue';
const STORE_NAME = 'submits';
const DB_VERSION = 1;

export interface QueuedSubmit {
  id?: number;
  url: string;
  method: string; // POST | PUT | PATCH
  body: unknown;
  contentType: string;
  /** Bearer-Token zum Sende-Zeitpunkt — JWT kann beim Replay schon abgelaufen sein. */
  token: string | null;
  /** Kurz-Beschreibung für die UI: "Tagesbericht 2026-05-17" o.ä. */
  label: string;
  createdAt: number;
  attempts: number;
  lastError?: string;
}

@Injectable({ providedIn: 'root' })
export class OfflineQueueService {
  private dbPromise: Promise<IDBDatabase> | null = null;

  /** Anzahl wartender Submits als Signal — direkt im UI bindbar. */
  readonly pendingCount = signal<number>(0);
  readonly pending = signal<QueuedSubmit[]>([]);
  readonly hasPending = computed(() => this.pendingCount() > 0);

  constructor() {
    // Initialer Load — falls beim App-Start was wartet
    this.refresh().catch(() => undefined);
  }

  private openDb(): Promise<IDBDatabase> {
    if (this.dbPromise) return this.dbPromise;
    this.dbPromise = new Promise((resolve, reject) => {
      if (typeof indexedDB === 'undefined') {
        reject(new Error('IndexedDB not available'));
        return;
      }
      const req = indexedDB.open(DB_NAME, DB_VERSION);
      req.onupgradeneeded = () => {
        const db = req.result;
        if (!db.objectStoreNames.contains(STORE_NAME)) {
          db.createObjectStore(STORE_NAME, { keyPath: 'id', autoIncrement: true });
        }
      };
      req.onsuccess = () => resolve(req.result);
      req.onerror = () => reject(req.error);
    });
    return this.dbPromise;
  }

  async add(item: Omit<QueuedSubmit, 'id' | 'createdAt' | 'attempts'>): Promise<number> {
    const db = await this.openDb();
    const payload: QueuedSubmit = {
      ...item,
      createdAt: Date.now(),
      attempts: 0,
    };
    return new Promise<number>((resolve, reject) => {
      const tx = db.transaction(STORE_NAME, 'readwrite');
      const req = tx.objectStore(STORE_NAME).add(payload);
      req.onsuccess = () => {
        const id = req.result as number;
        this.refresh().catch(() => undefined);
        resolve(id);
      };
      req.onerror = () => reject(req.error);
    });
  }

  async list(): Promise<QueuedSubmit[]> {
    const db = await this.openDb();
    return new Promise<QueuedSubmit[]>((resolve, reject) => {
      const tx = db.transaction(STORE_NAME, 'readonly');
      const req = tx.objectStore(STORE_NAME).getAll();
      req.onsuccess = () => resolve((req.result as QueuedSubmit[]) || []);
      req.onerror = () => reject(req.error);
    });
  }

  async remove(id: number): Promise<void> {
    const db = await this.openDb();
    return new Promise<void>((resolve, reject) => {
      const tx = db.transaction(STORE_NAME, 'readwrite');
      const req = tx.objectStore(STORE_NAME).delete(id);
      req.onsuccess = () => {
        this.refresh().catch(() => undefined);
        resolve();
      };
      req.onerror = () => reject(req.error);
    });
  }

  async update(item: QueuedSubmit): Promise<void> {
    if (item.id == null) return;
    const db = await this.openDb();
    return new Promise<void>((resolve, reject) => {
      const tx = db.transaction(STORE_NAME, 'readwrite');
      const req = tx.objectStore(STORE_NAME).put(item);
      req.onsuccess = () => {
        this.refresh().catch(() => undefined);
        resolve();
      };
      req.onerror = () => reject(req.error);
    });
  }

  async clearAll(): Promise<void> {
    const db = await this.openDb();
    return new Promise<void>((resolve, reject) => {
      const tx = db.transaction(STORE_NAME, 'readwrite');
      const req = tx.objectStore(STORE_NAME).clear();
      req.onsuccess = () => {
        this.refresh().catch(() => undefined);
        resolve();
      };
      req.onerror = () => reject(req.error);
    });
  }

  /** Liest die aktuelle Queue und aktualisiert die UI-Signals. */
  async refresh(): Promise<void> {
    try {
      const items = await this.list();
      items.sort((a, b) => a.createdAt - b.createdAt);
      this.pending.set(items);
      this.pendingCount.set(items.length);
    } catch {
      // IndexedDB nicht verfügbar (z.B. SSR) — silent fail
      this.pending.set([]);
      this.pendingCount.set(0);
    }
  }
}
