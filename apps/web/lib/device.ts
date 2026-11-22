import type { Mode } from "@vibechecker/contracts";
import type { Receipt } from "./check-stream";

export type DeviceCheck = Receipt & { mode?: Mode; text: string; createdAt: number; expiresAt: number };
export const deviceTtl = 30 * 24 * 60 * 60 * 1000;

async function transaction<T>(work: (store: IDBObjectStore, setResult: (value: T) => void) => void): Promise<T> {
  const db = await new Promise<IDBDatabase>((resolve, reject) => {
    const request = indexedDB.open("vibechecker", 1);
    request.onupgradeneeded = () => {
      const store = request.result.createObjectStore("checks", { keyPath: "checkId" });
      store.createIndex("expiresAt", "expiresAt");
      store.createIndex("createdAt", "createdAt");
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
  try {
    return await new Promise<T>((resolve, reject) => {
      const tx = db.transaction("checks", "readwrite");
      const store = tx.objectStore("checks");
      let value: T;
      tx.oncomplete = () => resolve(value);
      tx.onabort = () => reject(tx.error);
      const expired = store.index("expiresAt").openCursor(IDBKeyRange.upperBound(Date.now()));
      expired.onsuccess = () => {
        const cursor = expired.result;
        if (cursor) { cursor.delete(); cursor.continue(); }
        else work(store, (result) => { value = result; });
      };
    });
  } finally {
    db.close();
  }
}

export const latestCheck = (owner?:string|null) => transaction<DeviceCheck | undefined>((store, set) => {
  const request = store.index("createdAt").openCursor(null, "prev");
  request.onsuccess = () => {
    const cursor=request.result;
    if(cursor?.value.owner && cursor.value.owner!==owner) cursor.continue();
    else set(cursor?.value);
  };
});
export const saveCheck = (check: DeviceCheck) => transaction<void>((store) => { store.put(check); });
export const forgetChecks = () => transaction<void>((store) => { store.clear(); });
export const deviceChecks = () => transaction<DeviceCheck[]>((store,set) => {
  const request=store.index("createdAt").getAll();
  request.onsuccess=()=>set(request.result.reverse());
});
export const forgetOne = (id:string) => transaction<void>(store => {store.delete(id);});
export const forgetOwner = (owner:string) => transaction<void>(store=>{
  const request=store.openCursor();
  request.onsuccess=()=>{
    const cursor=request.result;
    if(cursor) {if(cursor.value.owner===owner) cursor.delete(); cursor.continue();}
  };
});
