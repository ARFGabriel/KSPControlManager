using System;
using System.Collections;
using System.Collections.Generic;
using System.Text;
using UnityEngine;

namespace KSP_AIAssistant
{
    /// <summary>
    /// Émetteur des données du VAB vers le centre de contrôle.
    ///
    /// Raison d'être : kRPC n'expose aucune API d'éditeur. Il est donc
    /// impossible de savoir depuis l'extérieur ce que le joueur est en train
    /// de construire. Ce composant, lui, tourne dans la scène et y a accès.
    ///
    /// Il n'envoie que la matière première — pièces, masses, moteurs,
    /// ergols. Tout le calcul de Δv reste côté backend, où il est déjà écrit
    /// et validé contre l'affichage du jeu. Dupliquer cette logique en C#
    /// serait le meilleur moyen de la voir diverger.
    /// </summary>
    [KSPAddon(KSPAddon.Startup.EditorAny, false)]
    public class VabEmitter : MonoBehaviour
    {
        private const string URL = "http://127.0.0.1:8000/api/vab";

        // Le joueur pose des pièces en continu : inutile d'émettre à chaque
        // image. Une seconde suffit largement pour que l'affichage suive.
        private const float PERIODE = 1.0f;

        // Le backend périme les données au bout de quinze secondes pour savoir
        // si on a quitté l'éditeur. Il faut donc réémettre régulièrement même
        // sans changement, sinon l'affichage se vide dès qu'on arrête de
        // construire alors que les chiffres restent parfaitement valables.
        private const float RAPPEL = 5.0f;

        private float prochainEnvoi;
        private float dernierEnvoi;
        private bool envoiEnCours;
        private int derniereEmpreinte;

        public void Update()
        {
            if (Time.realtimeSinceStartup < prochainEnvoi) return;
            prochainEnvoi = Time.realtimeSinceStartup + PERIODE;

            if (envoiEnCours) return;
            if (EditorLogic.fetch == null || EditorLogic.fetch.ship == null) return;

            ShipConstruct navire = EditorLogic.fetch.ship;

            int empreinte = Empreinte(navire);
            bool aChange = empreinte != derniereEmpreinte;
            bool tropVieux = Time.realtimeSinceStartup - dernierEnvoi > RAPPEL;
            if (!aChange && !tropVieux) return;

            derniereEmpreinte = empreinte;
            dernierEnvoi = Time.realtimeSinceStartup;

            string corps = ConstruireJson(navire);
            StartCoroutine(Envoyer(corps));
        }

        /// <summary>
        /// Signature grossière du vaisseau : change dès qu'on ajoute, retire
        /// ou re-étage une pièce.
        /// </summary>
        private int Empreinte(ShipConstruct navire)
        {
            int h = navire.parts.Count * 397;
            for (int i = 0; i < navire.parts.Count; i++)
            {
                Part p = navire.parts[i];
                h = (h * 31) ^ p.name.GetHashCode();
                h = (h * 31) ^ p.inverseStage;
            }
            return h;
        }

        // ------------------------------------------------------------------
        // Construction du JSON
        // ------------------------------------------------------------------
        private string ConstruireJson(ShipConstruct navire)
        {
            StringBuilder json = new StringBuilder(4096);
            json.Append("{");
            json.AppendFormat("\"nom\":\"{0}\",", Echapper(navire.shipName));
            json.AppendFormat("\"description\":\"{0}\",", Echapper(navire.shipDescription));
            json.AppendFormat("\"nombre_pieces\":{0},", navire.parts.Count);
            json.AppendFormat("\"etage_courant\":{0},", EtageMaximum(navire) + 1);
            json.Append("\"pieces\":[");

            for (int i = 0; i < navire.parts.Count; i++)
            {
                if (i > 0) json.Append(",");
                json.Append(PieceEnJson(navire.parts[i], i));
            }

            json.Append("],");
            json.Append(LignesErgolEnJson(navire));
            json.Append(",");
            json.Append(EquipementsEnJson(navire));
            json.Append("}");
            return json.ToString();
        }

        /// <summary>
        /// Recensement des équipements dont l'absence condamne une mission.
        ///
        /// Ces trois oublis sont les plus courants et les plus coûteux : une
        /// sonde sans production électrique meurt dès ses batteries vides et
        /// devient un débris incontrôlable ; sans antenne elle ne transmet
        /// rien ; sans parachute un équipage ne rentre pas.
        ///
        /// On compte ici, le backend juge.
        /// </summary>
        private string EquipementsEnJson(ShipConstruct navire)
        {
            int panneaux = 0, generateurs = 0, antennes = 0, parachutes = 0;
            int alternateurs = 0, places = 0;

            foreach (Part piece in navire.parts)
            {
                places += piece.CrewCapacity;

                if (piece.Modules == null) continue;
                for (int i = 0; i < piece.Modules.Count; i++)
                {
                    PartModule m = piece.Modules[i];
                    if (m == null) continue;
                    switch (m.moduleName)
                    {
                        case "ModuleDeployableSolarPanel": panneaux++; break;
                        // Les RTG et générateurs à carburant produisent en continu.
                        case "ModuleGenerator": generateurs++; break;
                        // L'alternateur ne produit que moteur allumé : il ne
                        // sauve pas une sonde en vol balistique.
                        case "ModuleAlternator": alternateurs++; break;
                        case "ModuleDataTransmitter": antennes++; break;
                        case "ModuleParachute": parachutes++; break;
                    }
                }
            }

            StringBuilder json = new StringBuilder(160);
            json.Append("\"equipements\":{");
            json.AppendFormat("\"panneaux_solaires\":{0},", panneaux);
            json.AppendFormat("\"generateurs\":{0},", generateurs);
            json.AppendFormat("\"alternateurs\":{0},", alternateurs);
            json.AppendFormat("\"antennes\":{0},", antennes);
            json.AppendFormat("\"parachutes\":{0},", parachutes);
            json.AppendFormat("\"places_equipage\":{0}", places);
            json.Append("}");
            return json.ToString();
        }

        /// <summary>
        /// Conduites de carburant, indispensables pour l'asparagus staging.
        ///
        /// Sans elles, un lanceur comme la Kerbal X est incalculable : les
        /// propulseurs latéraux alimentent le moteur central, se vident donc
        /// en premier, et sont largués pendant que le central poursuit. Un
        /// modèle qui les ignore fait brûler chaque groupe séparément et se
        /// trompe lourdement.
        ///
        /// Une conduite est une CompoundPart : sa pièce d'attache est la
        /// source, sa cible est la destination du carburant.
        /// </summary>
        private string LignesErgolEnJson(ShipConstruct navire)
        {
            StringBuilder json = new StringBuilder(256);
            json.Append("\"lignes_ergol\":[");

            bool premiere = true;
            for (int i = 0; i < navire.parts.Count; i++)
            {
                CompoundPart conduite = navire.parts[i] as CompoundPart;
                if (conduite == null || conduite.target == null) continue;
                if (!EstConduiteErgol(conduite)) continue;

                int source = navire.parts.IndexOf(conduite.parent);
                int cible = navire.parts.IndexOf(conduite.target);
                if (source < 0 || cible < 0) continue;

                if (!premiere) json.Append(",");
                premiere = false;
                json.AppendFormat("{{\"de\":{0},\"vers\":{1}}}", source, cible);
            }

            json.Append("]");
            return json.ToString();
        }

        private int EtageMaximum(ShipConstruct navire)
        {
            int max = 0;
            foreach (Part p in navire.parts)
                if (p.inverseStage > max) max = p.inverseStage;
            return max;
        }

        private string PieceEnJson(Part piece, int index)
        {
            StringBuilder json = new StringBuilder(512);
            json.Append("{");
            json.AppendFormat("\"index\":{0},", index);
            json.AppendFormat("\"titre\":\"{0}\",", Echapper(piece.partInfo != null ? piece.partInfo.title : piece.name));
            // Les masses du jeu sont en tonnes ; le backend travaille en kg.
            json.AppendFormat("\"masse_seche\":{0},", Nombre(piece.mass * 1000f));
            json.AppendFormat("\"etage\":{0},", piece.inverseStage);
            json.AppendFormat("\"etage_decouplage\":{0},", EtageDecouplage(piece));

            // --- Ressources ---
            json.Append("\"ressources\":[");
            bool premiere = true;
            foreach (PartResource r in piece.Resources)
            {
                if (r.amount <= 0) continue;
                if (!premiere) json.Append(",");
                premiere = false;
                json.Append("{");
                json.AppendFormat("\"nom\":\"{0}\",", Echapper(r.resourceName));
                json.AppendFormat("\"quantite\":{0},", Nombre((float)r.amount));
                json.AppendFormat("\"densite\":{0}", Nombre(r.info != null ? r.info.density * 1000f : 0f));
                json.Append("}");
            }
            json.Append("]");

            // --- Moteur ---
            ModuleEngines moteur = piece.FindModuleImplementing<ModuleEngines>();
            if (moteur != null)
            {
                float limiteur = moteur.thrustPercentage / 100f;
                json.Append(",\"moteur\":{");
                // maxThrust est en kN, le backend attend des newtons.
                json.AppendFormat("\"poussee_max\":{0},", Nombre(moteur.maxThrust * 1000f * limiteur));
                json.AppendFormat("\"isp_vide\":{0},", Nombre(IspA(moteur, 0f)));
                json.AppendFormat("\"isp_sol\":{0},", Nombre(IspA(moteur, 1f)));
                json.Append("\"ergols\":[");
                for (int i = 0; i < moteur.propellants.Count; i++)
                {
                    if (i > 0) json.Append(",");
                    Propellant erg = moteur.propellants[i];
                    json.Append("{");
                    json.AppendFormat("\"nom\":\"{0}\",", Echapper(erg.name));
                    json.AppendFormat("\"ratio\":{0}", Nombre(erg.ratio));
                    json.Append("}");
                }
                json.Append("]}");
            }

            json.Append("}");
            return json.ToString();
        }

        /// <summary>
        /// Étage auquel la pièce est larguée.
        ///
        /// On remonte l'arbre vers la racine : le premier découpleur croisé
        /// est celui qui détachera cette pièce. Sans cette information, le
        /// calcul de Δv attribuerait à chaque étage la masse de tout le
        /// vaisseau, ce qui fausserait tout.
        /// </summary>
        private int EtageDecouplage(Part piece)
        {
            Part courante = piece;
            while (courante != null)
            {
                if (EstDecoupleur(courante))
                    return courante.inverseStage;
                courante = courante.parent;
            }
            return -1; // jamais larguée
        }

        /// <summary>
        /// Distingue une conduite de carburant d'une simple entretoise, qui
        /// est elle aussi une CompoundPart avec une cible.
        ///
        /// On compare le nom du module plutôt que son type : CModuleFuelLine
        /// ne vit pas dans les assemblys que ce projet référence, et le nom
        /// fonctionne aussi pour les conduites ajoutées par des mods.
        /// </summary>
        private bool EstConduiteErgol(Part piece)
        {
            if (piece.Modules == null) return false;
            for (int i = 0; i < piece.Modules.Count; i++)
            {
                PartModule module = piece.Modules[i];
                if (module == null) continue;
                if (module.moduleName == "CModuleFuelLine") return true;
            }
            return false;
        }

        private bool EstDecoupleur(Part piece)
        {
            return piece.FindModuleImplementing<ModuleDecouple>() != null
                || piece.FindModuleImplementing<ModuleAnchoredDecoupler>() != null;
        }

        /// <summary>Impulsion spécifique à une pression donnée, en secondes.</summary>
        private float IspA(ModuleEngines moteur, float pressionAtm)
        {
            if (moteur.atmosphereCurve == null) return 0f;
            return moteur.atmosphereCurve.Evaluate(pressionAtm);
        }

        // ------------------------------------------------------------------
        // Envoi
        // ------------------------------------------------------------------
        private IEnumerator Envoyer(string corps)
        {
            envoiEnCours = true;
            bool termine = false;
            string erreur = "";

            System.Threading.ThreadPool.QueueUserWorkItem(state =>
            {
                try
                {
                    using (System.Net.WebClient client = new System.Net.WebClient())
                    {
                        client.Headers[System.Net.HttpRequestHeader.ContentType] = "application/json";
                        client.Encoding = Encoding.UTF8;
                        client.UploadString(URL, "POST", corps);
                    }
                }
                catch (Exception e)
                {
                    erreur = e.Message;
                }
                termine = true;
            });

            while (!termine) yield return null;

            // Le centre de contrôle n'est pas forcément lancé : c'est un cas
            // normal, pas une panne. On ne pollue pas la console pour ça.
            if (!string.IsNullOrEmpty(erreur))
                Debug.Log("[AIAssistant] VAB non transmis (centre de controle absent ?) : " + erreur);

            envoiEnCours = false;
        }

        // ------------------------------------------------------------------
        private static string Echapper(string texte)
        {
            if (string.IsNullOrEmpty(texte)) return "";
            return texte.Replace("\\", "\\\\").Replace("\"", "\\\"")
                        .Replace("\n", " ").Replace("\r", " ").Replace("\t", " ");
        }

        /// <summary>
        /// Nombre au format JSON, en culture invariante.
        /// En français, ToString() produit une virgule décimale, ce qui casse
        /// le JSON de façon très difficile à diagnostiquer.
        /// </summary>
        private static string Nombre(float valeur)
        {
            if (float.IsNaN(valeur) || float.IsInfinity(valeur)) return "0";
            return valeur.ToString("0.######", System.Globalization.CultureInfo.InvariantCulture);
        }
    }
}
