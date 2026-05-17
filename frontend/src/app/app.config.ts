import { ApplicationConfig, isDevMode, provideBrowserGlobalErrorListeners } from '@angular/core';
import { provideHttpClient, withInterceptors } from '@angular/common/http';
import { provideRouter, withComponentInputBinding } from '@angular/router';
import { provideServiceWorker } from '@angular/service-worker';

import { routes } from './app.routes';
import { authInterceptor } from './core/services/auth.interceptor';
import { offlineQueueInterceptor } from './core/services/offline-queue.interceptor';

export const appConfig: ApplicationConfig = {
  providers: [
    provideBrowserGlobalErrorListeners(),
    // Reihenfolge wichtig: offlineQueue UMSCHLIESST auth — der Auth-Interceptor
    // setzt den Token, danach kann der Queue-Interceptor das Network-Verhalten
    // abfangen und ggf. queuen.
    provideHttpClient(withInterceptors([authInterceptor, offlineQueueInterceptor])),
    provideRouter(routes, withComponentInputBinding()),
    provideServiceWorker('ngsw-worker.js', {
      enabled: !isDevMode(),
      registrationStrategy: 'registerWhenStable:30000',
    }),
  ],
};
