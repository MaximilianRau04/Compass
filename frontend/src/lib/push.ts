/** Push subscription of this browser. The service worker (push-sw.js) shows the notifications. */

export type PushState = 'unsupported' | 'denied' | 'off' | 'on'

export function pushSupported(): boolean {
  return 'serviceWorker' in navigator && 'PushManager' in window && 'Notification' in window
}

async function registration(): Promise<ServiceWorkerRegistration> {
  return navigator.serviceWorker.ready
}

export async function currentSubscription(): Promise<PushSubscription | null> {
  if (!pushSupported()) return null
  return (await registration()).pushManager.getSubscription()
}

export async function pushState(): Promise<PushState> {
  if (!pushSupported()) return 'unsupported'
  if (Notification.permission === 'denied') return 'denied'
  return (await currentSubscription()) ? 'on' : 'off'
}

function keyBytes(base64url: string): Uint8Array<ArrayBuffer> {
  const padded = (base64url + '='.repeat((4 - (base64url.length % 4)) % 4)).replace(/-/g, '+').replace(/_/g, '/')
  const raw = atob(padded)
  const out = new Uint8Array(new ArrayBuffer(raw.length))
  for (let i = 0; i < raw.length; i++) out[i] = raw.charCodeAt(i)
  return out
}

/** Ask for permission and subscribe; null when the user said no. */
export async function subscribePush(publicKey: string): Promise<PushSubscriptionJSON | null> {
  if ((await Notification.requestPermission()) !== 'granted') return null
  const reg = await registration()
  const existing = await reg.pushManager.getSubscription()
  const sub =
    existing ?? (await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: keyBytes(publicKey) }))
  return sub.toJSON()
}

export async function unsubscribePush(): Promise<string | null> {
  const sub = await currentSubscription()
  if (!sub) return null
  await sub.unsubscribe()
  return sub.endpoint
}
