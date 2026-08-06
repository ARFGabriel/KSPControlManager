/** Adresse du backend.
 *
 *  En développement le dashboard tourne sur le port de Vite (5173) alors que
 *  le backend écoute sur 8000 ; une fois compilé, les deux sont servis par la
 *  même origine. Cette fonction était recopiée dans chaque panneau — elle vit
 *  maintenant à un seul endroit.
 */
export function apiUrl(path: string): string {
  const host = location.port === "5173" ? `${location.hostname}:8000` : location.host;
  return `${location.protocol}//${host}${path}`;
}

/** GET JSON, en rendant `null` plutôt qu'en levant : aucun panneau ne doit
 *  faire tomber la page parce que le backend a hoqueté. */
export async function getJson<T>(path: string): Promise<T | null> {
  try {
    const reponse = await fetch(apiUrl(path));
    if (!reponse.ok) return null;
    return (await reponse.json()) as T;
  } catch {
    return null;
  }
}
