import { Pool } from 'pg';
import {
  AuthenticationCreds,
  AuthenticationState,
  SignalDataTypeMap,
  initAuthCreds,
  proto,
  BufferJSON,
} from '@whiskeysockets/baileys';

export async function usePgAuthState(pool: Pool): Promise<{
  state: AuthenticationState;
  saveCreds: () => Promise<void>;
}> {
  const readData = async (id: string): Promise<any | null> => {
    const { rows } = await pool.query('SELECT data FROM whatsapp_sessions WHERE id = $1', [id]);
    if (rows.length === 0) return null;
    return JSON.parse(JSON.stringify(rows[0].data), BufferJSON.reviver);
  };

  const writeData = async (id: string, data: any): Promise<void> => {
    const json = JSON.parse(JSON.stringify(data, BufferJSON.replacer));
    await pool.query(
      `INSERT INTO whatsapp_sessions (id, data, updated_at) VALUES ($1, $2, NOW())
       ON CONFLICT (id) DO UPDATE SET data = $2, updated_at = NOW()`,
      [id, json]
    );
  };

  const removeData = async (id: string): Promise<void> => {
    await pool.query('DELETE FROM whatsapp_sessions WHERE id = $1', [id]);
  };

  const creds: AuthenticationCreds = (await readData('creds')) || initAuthCreds();

  return {
    state: {
      creds,
      keys: {
        get: async <T extends keyof SignalDataTypeMap>(type: T, ids: string[]) => {
          const data: { [id: string]: SignalDataTypeMap[T] } = {};
          for (const id of ids) {
            const value = await readData(`${type}-${id}`);
            if (value) {
              if (type === 'app-state-sync-key' && value) {
                data[id] = proto.Message.AppStateSyncKeyData.fromObject(value) as any;
              } else {
                data[id] = value;
              }
            }
          }
          return data;
        },
        set: async (data: any) => {
          const tasks: Promise<void>[] = [];
          for (const category in data) {
            for (const id in data[category]) {
              const value = data[category][id];
              const key = `${category}-${id}`;
              tasks.push(value ? writeData(key, value) : removeData(key));
            }
          }
          await Promise.all(tasks);
        },
      },
    },
    saveCreds: () => writeData('creds', creds),
  };
}
