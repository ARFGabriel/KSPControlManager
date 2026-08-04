import { useEffect, useRef, useState } from "react";

import { Panel } from "./ui";
import { useRadio, type Persona } from "../useRadio";

const LABELS: Record<string, string> = {
  pilote: "Vous",
  ground: "Kerbal Space Center",
  crew: "Équipage",
};

export function RadioPanel() {
  const { entries, status, confirmation, waiting, send, respond, reset } = useRadio();
  const [persona, setPersona] = useState<Persona>("crew");
  const [text, setText] = useState("");
  const logRef = useRef<HTMLDivElement>(null);

  // On garde toujours le dernier échange visible.
  useEffect(() => {
    logRef.current?.scrollTo({ top: logRef.current.scrollHeight });
  }, [entries, confirmation, waiting]);

  const submit = () => {
    const value = text.trim();
    if (!value || waiting) return;
    send(persona, value);
    setText("");
  };

  return (
    <Panel
      title="Radio"
      extra={
        status ? (
          <span style={{ color: status.available ? "var(--dim)" : "var(--red)" }}>
            {status.available ? status.model : "aucun modèle configuré"}
          </span>
        ) : null
      }
    >
      <div className="radio-tabs">
        <button
          className={persona === "ground" ? "active" : ""}
          onClick={() => setPersona("ground")}
        >
          Sol
        </button>
        <button
          className={persona === "crew" ? "active" : ""}
          onClick={() => setPersona("crew")}
        >
          Bord
        </button>
        <span style={{ flex: 1 }} />
        <button onClick={reset} title="Effacer la conversation">
          Effacer
        </button>
      </div>

      <p className="radio-hint">
        {persona === "ground"
          ? "Le sol conseille et surveille. Il ne peut agir sur rien."
          : "L'équipage exécute les commandes à bord."}
      </p>

      <div className="radio-log" ref={logRef}>
        {entries.length === 0 && (
          <div className="empty">
            Canal ouvert. Parlez au sol ou à l'équipage.
          </div>
        )}

        {entries.map((e) => {
          if (e.kind === "command") {
            return (
              <div key={e.key} className={`radio-cmd ${e.ok ? "ok" : "ko"}`}>
                <span className="tag">{e.ok ? "EXÉCUTÉ" : "ÉCHEC"}</span>
                <code>{e.name}</code>
                <div className="detail">{e.text}</div>
              </div>
            );
          }
          if (e.kind === "error") {
            return (
              <div key={e.key} className="radio-error">
                {e.text}
              </div>
            );
          }
          return (
            <div key={e.key} className={`radio-msg ${e.persona}`}>
              <div className="who">{LABELS[e.persona ?? ""] ?? e.persona}</div>
              <div className="body">{e.text}</div>
            </div>
          );
        })}

        {waiting && <div className="radio-waiting">…transmission en cours</div>}
      </div>

      {/* Une action irréversible ne part jamais sans accord explicite. */}
      {confirmation && (
        <div className="radio-confirm">
          <div className="head">Confirmation requise</div>
          <code>
            {confirmation.name}
            {Object.keys(confirmation.arguments).length > 0 &&
              ` ${JSON.stringify(confirmation.arguments)}`}
          </code>
          <p>{confirmation.description}</p>
          <div className="actions">
            <button className="deny" onClick={() => respond(confirmation.id, false)}>
              Refuser
            </button>
            <button className="allow" onClick={() => respond(confirmation.id, true)}>
              Confirmer
            </button>
          </div>
        </div>
      )}

      <div className="radio-input">
        <input
          value={text}
          placeholder={
            persona === "ground" ? "Message au sol…" : "Message à l'équipage…"
          }
          onChange={(event) => setText(event.target.value)}
          onKeyDown={(event) => event.key === "Enter" && submit()}
          disabled={!status?.available}
        />
        <button onClick={submit} disabled={waiting || !status?.available}>
          Émettre
        </button>
      </div>

      {status && !status.available && (
        <p className="radio-hint" style={{ color: "var(--red)" }}>
          Renseigne GEMINI_API_KEY dans backend/.env, puis relance le backend.
        </p>
      )}
    </Panel>
  );
}
