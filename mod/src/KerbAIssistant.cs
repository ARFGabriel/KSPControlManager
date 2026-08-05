using System;
using System.Collections;
using System.Text;
using UnityEngine;
using UnityEngine.Networking;
using KSP.UI.Screens;

namespace KSP_AIAssistant
{
    [KSPAddon(KSPAddon.Startup.EditorAny, false)]
    public class VABAssistantPlugin : MonoBehaviour
    {
        private Rect windowRect = new Rect(20, 100, 350, 450); 
        private string chatInput = "";
        private string chatLog = "IA: Bonjour ! Prêt à construire cette fusée ?\n";
        private bool showWindow = true; 

        // La clé n'est JAMAIS écrite dans le code source : elle serait compilée
        // dans la DLL distribuée et donc lisible par n'importe qui.
        // Elle est lue au démarrage depuis GameData/AIAssistant/apikey.txt,
        // un fichier qui reste local et n'est pas versionné.
        private string apiKey = null;
        private string apiURL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent";

        /// <summary>
        /// Charge la clé API depuis le fichier local, une seule fois.
        /// Renvoie false si le fichier est absent ou vide.
        /// </summary>
        private bool ChargerCle()
        {
            if (!string.IsNullOrEmpty(apiKey)) return true;

            try
            {
                // Deux chemins possibles, essayés dans l'ordre. Selon la façon
                // dont KSP charge le plugin, Assembly.Location peut être vide :
                // on retombe alors sur le chemin d'installation du jeu, qui est
                // toujours renseigné.
                string[] candidats = new string[]
                {
                    CheminPresDeLaDll(),
                    KSPUtil.ApplicationRootPath + "GameData/AIAssistant/apikey.txt"
                };

                foreach (string chemin in candidats)
                {
                    if (string.IsNullOrEmpty(chemin)) continue;
                    if (!System.IO.File.Exists(chemin)) continue;

                    apiKey = System.IO.File.ReadAllText(chemin).Trim();
                    if (!string.IsNullOrEmpty(apiKey))
                    {
                        Debug.Log("[AIAssistant] Clé API chargée depuis " + chemin);
                        return true;
                    }
                }

                Debug.LogError("[AIAssistant] Clé API introuvable. Crée le fichier : "
                    + KSPUtil.ApplicationRootPath + "GameData/AIAssistant/apikey.txt");
                return false;
            }
            catch (System.Exception e)
            {
                Debug.LogError("[AIAssistant] Lecture de la clé impossible : " + e.Message);
                return false;
            }
        }

        /// <summary>
        /// Chemin du apikey.txt posé à côté de la DLL. Peut renvoyer null si
        /// l'assembly n'expose pas son emplacement.
        /// </summary>
        private string CheminPresDeLaDll()
        {
            try
            {
                string emplacement = System.Reflection.Assembly.GetExecutingAssembly().Location;
                if (string.IsNullOrEmpty(emplacement)) return null;

                string dossier = System.IO.Path.GetDirectoryName(emplacement);
                if (string.IsNullOrEmpty(dossier)) return null;

                return System.IO.Path.Combine(dossier, "apikey.txt");
            }
            catch
            {
                return null;
            }
        }

        public void OnGUI()
        {
            if (showWindow)
            {
                windowRect = GUILayout.Window(1, windowRect, DrawWindow, "Assistant IA - KSP");
            }
        }

        private void DrawWindow(int windowID)
        {
            GUILayout.Box(chatLog, GUILayout.Height(350));
            chatInput = GUILayout.TextField(chatInput);

            GUILayout.BeginHorizontal();
            if (GUILayout.Button("Analyser Fusée"))
            {
                AnalyserVaisseau();
            }
            if (GUILayout.Button("Envoyer à l'IA"))
            {
                EnvoyerMessage();
            }
            GUILayout.EndHorizontal();

            GUI.DragWindow();
        }

        private void AnalyserVaisseau()
        {
            if (EditorLogic.fetch != null && EditorLogic.fetch.ship != null)
            {
                int partCount = EditorLogic.fetch.ship.parts.Count;
                float totalMass = EditorLogic.fetch.ship.GetTotalMass();
                chatLog += $"\nSystème : [Vaisseau] Pièces: {partCount}, Masse: {totalMass}t.";
            }
        }

        private void EnvoyerMessage()
        {
            if (!string.IsNullOrEmpty(chatInput))
            {
                chatLog += $"\nToi: {chatInput}";
                string messageAEnvoyer = chatInput;
                chatInput = ""; // On vide la zone de texte
                
                // On lance la requête internet en arrière-plan !
                StartCoroutine(RequeteIA(messageAEnvoyer));
            }
        }

        // C'est ici que se trouve la Coroutine qui gère internet
        private IEnumerator RequeteIA(string message)
        {
            if (!ChargerCle())
            {
                chatLog += "\nSystème : Clé API introuvable (voir console Alt+F12).";
                yield break;
            }

            chatLog += "\nIA: (Réflexion en cours...)";

            // Nettoyage du message
            string messagePropre = message.Replace("\"", "\\\"").Replace("\n", " ");
            string contexte = "Tu es un assistant pour le jeu Kerbal Space Program. Réponds brièvement. ";
            string jsonData = "{\"contents\":[{\"parts\":[{\"text\":\"" + contexte + messagePropre + "\"}]}]}";

            string reponseBrute = "";
            string erreur = "";
            bool requeteTerminee = false;

            System.Threading.ThreadPool.QueueUserWorkItem(state =>
            {
                try
                {
                    System.Net.ServicePointManager.SecurityProtocol = System.Net.SecurityProtocolType.Tls12;
                    using (System.Net.WebClient client = new System.Net.WebClient())
                    {
                        client.Headers[System.Net.HttpRequestHeader.ContentType] = "application/json";
                        client.Encoding = System.Text.Encoding.UTF8; 
                        reponseBrute = client.UploadString(apiURL + "?key=" + apiKey, "POST", jsonData);
                    }
                }
                catch (System.Net.WebException e)
                {
                    // C'EST ICI QU'ON EXTRAIT LE VRAI MESSAGE DE GOOGLE
                    erreur = "Erreur HTTP : " + e.Message;
                    if (e.Response != null)
                    {
                        using (var stream = e.Response.GetResponseStream())
                        using (var reader = new System.IO.StreamReader(stream))
                        {
                            erreur += "\nRéponse de Google : " + reader.ReadToEnd();
                        }
                    }
                }
                catch (System.Exception e)
                {
                    erreur = "Erreur système : " + e.Message;
                }
                
                requeteTerminee = true;
            });

            // On attend la fin de la tâche
            while (!requeteTerminee)
            {
                yield return null; 
            }

            // On efface le message d'attente
            chatLog = chatLog.Replace("\nIA: (Réflexion en cours...)", "");

            if (!string.IsNullOrEmpty(erreur))
            {
                // On affiche un résumé court dans le chat de la fenêtre
                chatLog += "\nSystème : Erreur de connexion (Voir console Alt+F12)";
                
                // On écrit TOUT LE DETAIL dans la console de développement de KSP
                Debug.LogError("[AIAssistant] --- DÉBUT DE L'ERREUR ---");
                Debug.LogError("[AIAssistant] MESSAGE : " + erreur);
                Debug.LogError("[AIAssistant] JSON ENVOYÉ : " + jsonData);
                Debug.LogError("[AIAssistant] --- FIN DE L'ERREUR ---");
            }
            else
            {
                chatLog += "\nIA: " + ExtraireTexte(reponseBrute);
            }
        }

        // Fonction simple pour lire le format JSON renvoyé par l'IA
        private string ExtraireTexte(string json)
        {
            try {
                // On cherche où commence le texte de la réponse
                int startIndex = json.IndexOf("\"text\": \"") + 9;
                if (startIndex > 8) {
                    int endIndex = json.IndexOf("\"", startIndex);
                    string texte = json.Substring(startIndex, endIndex - startIndex);
                    return texte.Replace("\\n", "\n").Replace("\\\"", "\"");
                }
            } catch { }
            return "Oups, je n'ai pas pu lire la réponse.";
        }
    }
}