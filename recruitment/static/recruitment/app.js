import { validatePayload, searchLoaded } from "./payload.js";

const age = window.age;
const $ = id => document.getElementById(id);

const state = {
  bootstrap: null,
  rows: [],
  cursor: null,
  finished: false,
  total: 0,
  failed: 0,
  busy: false,
  generation: 0
};

function node(tag, text) {
  const result = document.createElement(tag);
  if (text !== undefined) result.textContent = text;
  return result;
}

function status(message) {
  $("message").textContent = message;
}

function problem(message) {
  $("problem").textContent = message;
}

async function run(action) {
  problem("");
  try {
    await action();
  } catch (error) {
    problem(error.message || "The operation failed.");
  }
}

function button(text, action) {
  const result = node("button", text);
  result.type = "button";
  result.addEventListener("click", () => run(action));
  return result;
}

async function api(path, data) {
  const options = {
    credentials: "same-origin",
    cache: "no-store"
  };

  if (data !== undefined) {
    options.method = "POST";
    options.headers = {
      "Content-Type": "application/json",
      "X-CSRFToken": document.querySelector(
        '#logout input[name="csrfmiddlewaretoken"]'
      ).value
    };
    options.body = JSON.stringify(data);
  }

  const response = await fetch(path, options);
  if (!response.ok) {
    let message = "The request failed.";
    try {
      message = (await response.json()).error || message;
    } catch {
      // Do not expose arbitrary server responses.
    }
    throw new Error(message);
  }
  return response.json();
}

function base64(bytes) {
  let result = "";
  for (const byte of bytes) result += String.fromCharCode(byte);
  return btoa(result);
}

function unbase64(value) {
  return Uint8Array.from(atob(value), character => character.charCodeAt(0));
}

const definitions = {
  experience: [
    ["role", "Role or role category", "text", 120],
    ["duration_months", "Duration in months", "number", null],
    ["responsibilities", "Relevant responsibilities", "textarea", 2000],
    ["accomplishments", "Relevant accomplishments", "textarea", 2000]
  ],
  education: [
    ["qualification", "Qualification level", "text", 120],
    ["subject", "Subject or field of study", "text", 120]
  ],
  skills: [
    ["name", "Skill name", "text", 100],
    ["proficiency", "Proficiency, optional", "text", 100],
    ["evidence", "Relevant evidence, optional", "textarea", 1000]
  ]
};

let sequence = 0;

function addEntry(section) {
  if ($(section).children.length >= 50) {
    throw new Error("This section already has 50 entries.");
  }

  const fieldset = node("fieldset");
  fieldset.append(node("legend", `New ${section} entry`));

  for (const [name, labelText, type, maximum] of definitions[section]) {
    const id = `structured-field-${++sequence}`;
    const label = node("label", labelText);
    label.htmlFor = id;

    const input = node(type === "textarea" ? "textarea" : "input");
    if (type !== "textarea") input.type = type;
    input.id = id;
    input.dataset.field = name;
    input.required = !["proficiency", "evidence"].includes(name);

    if (maximum) input.maxLength = maximum;
    if (type === "number") {
      input.min = "0";
      input.max = "1200";
      input.step = "1";
    }

    fieldset.append(label, input);
  }

  fieldset.append(button("Remove entry", () => fieldset.remove()));
  $(section).append(fieldset);
}

function readPayload() {
  const payload = { schema_version: 1 };

  for (const section of Object.keys(definitions)) {
    payload[section] = [...$(section).children].map(fieldset => {
      const entry = {};
      for (const input of fieldset.querySelectorAll("[data-field]")) {
        const name = input.dataset.field;
        const value = input.value.trim();

        if (value || !["proficiency", "evidence"].includes(name)) {
          entry[name] = name === "duration_months" ? Number(value) : value;
        }
      }
      return entry;
    });
  }

  return validatePayload(payload);
}

function company() {
  return state.bootstrap.companies.find(
    item => item.id === Number($("company").value)
  );
}

function renderRecipients() {
  $("verified").checked = false;
  $("recipients").replaceChildren(node("legend", "Intended recipients"));

  for (const recipient of company()?.recipients || []) {
    const label = node("label");
    const input = node("input");
    input.type = "checkbox";
    input.value = recipient.key_id;

    input.addEventListener("change", () => {
      $("verified").checked = false;
    });

    label.append(
      input,
      document.createTextNode(
        ` Recipient ${recipient.recipient_id}; ` +
        `version ${recipient.version}; ` +
        `public key ${recipient.public_key}; ` +
        `SHA-256 fingerprint ${recipient.fingerprint}`
      )
    );

    $("recipients").append(label);
  }
}

async function history() {
  const response = await api("/api/submissions/");
  $("history").replaceChildren();

  for (const item of response.items) {
    const card = node("article");
    card.append(
      node("h3", `Submission ${item.id}`),
      node("p", `${item.company} — ${item.created_at} — ${item.status}`)
    );

    for (const access of item.accesses) {
      card.append(node(
        "p",
        `Recipient ${access.recipient_id}: ` +
        (access.revoked ? "revoked" : "authorized")
      ));

      if (!access.revoked) {
        card.append(button("Revoke future retrieval for this access", async () => {
          await api(`/api/access/${access.id}/revoke/`, {});
          await history();
          status("Future retrieval revoked. Downloaded copies remain.");
        }));
      }
    }

    card.append(button("Delete submission", async () => {
      await api(`/api/submissions/${item.id}/delete/`, {});
      await history();
      await contacts();
      status("Submission deleted from the live database.");
    }));

    $("history").append(card);
  }
}

async function contacts() {
  const response = await api("/api/contacts/");
  $("contacts").replaceChildren();

  for (const item of response.items) {
    const card = node("article");
    card.append(node(
      "p",
      `${item.company || "Submission " + item.submission_id}: ${item.status}` +
      (item.requester_id ? `; requester ${item.requester_id}` : "")
    ));

    if (state.bootstrap.kind === "recruit" && item.status === "pending") {
      for (const answer of ["accepted", "declined"]) {
        card.append(button(
          answer === "accepted" ? "Accept and share my email" : "Decline",
          async () => {
            await api(`/api/contacts/${item.id}/respond/`, {
              status: answer
            });
            await contacts();
          }
        ));
      }
    }

    if (item.email) {
      card.append(node("p", `Approved contact email: ${item.email}`));
    }

    $("contacts").append(card);
  }
}

function results() {
  const matches = searchLoaded(state.rows, $("search").value);

  $("scope").textContent =
    `${state.rows.length} decrypted of ${state.total} currently received. ` +
    `${matches.length} match. ${state.failed} failed decryption or validation. ` +
    "Search covers only this browser's loaded, decrypted subset. " +
    "Refresh local review to reflect access changes.";

  $("results").replaceChildren();

  for (const item of matches) {
    const card = node("article");
    card.append(
      node("h3", `Anonymous submission ${item.id}`),
      node("p", `Received ${item.created_at}`)
    );

    for (const section of ["experience", "education", "skills"]) {
      card.append(node("h4", section));
      for (const entry of item.payload[section]) {
        const list = node("dl");
        for (const [name, value] of Object.entries(entry)) {
          list.append(
            node("dt", name.replaceAll("_", " ")),
            node("dd", String(value))
          );
        }
        card.append(list);
      }
    }

    card.append(button("Request contact", async () => {
      await api(`/api/submissions/${item.id}/contact/`, {});
      await contacts();
      status("Contact request recorded.");
    }));

    $("results").append(card);
  }
}

function clearReview() {
  state.generation++;
  state.rows = [];
  state.cursor = null;
  state.finished = false;
  state.total = 0;
  state.failed = 0;
  $("identity-file").value = "";
  $("search").value = "";
  $("load").disabled = state.busy;
  results();
}

async function loadPage() {
  if (state.busy || state.finished) return;

  const file = $("identity-file").files[0];
  if (!file || file.size > 16_384) {
    throw new Error("Select a local native age identity file under 16 KiB.");
  }

  state.busy = true;
  $("load").disabled = true;
  const generation = state.generation;

  let decrypter;
  let identityText;

  try {
    identityText = await file.text();
    if (generation !== state.generation) return;

    const identities = identityText.split(/\r?\n/)
      .map(line => line.trim())
      .filter(line => line && !line.startsWith("#"));

    if (
      identities.length < 1 ||
      identities.length > 10 ||
      identities.some(value => !value.startsWith("AGE-SECRET-KEY-1"))
    ) {
      throw new Error("Use a native age identity file, not a public key.");
    }

    decrypter = new age.Decrypter();
    for (const identity of identities) decrypter.addIdentity(identity);

    const suffix = state.cursor
      ? "?after=" + encodeURIComponent(state.cursor)
      : "";

    const response = await api("/api/submissions/" + suffix);
    if (generation !== state.generation) return;

    state.total = response.total;

    for (const item of response.items) {
      try {
        const ciphertext = unbase64(item.ciphertext);
        if (ciphertext.length > 262_144) throw new Error("Oversized ciphertext.");

        const plaintext = await decrypter.decrypt(ciphertext, "text");
        if (generation !== state.generation) return;

        if (new TextEncoder().encode(plaintext).length > 100_000) {
          throw new Error("Oversized payload.");
        }

        const payload = validatePayload(JSON.parse(plaintext));

        if (!state.rows.some(row => row.id === item.id)) {
          state.rows.push({
            id: item.id,
            created_at: item.created_at,
            payload
          });
        }
      } catch {
        if (generation !== state.generation) return;
        state.failed++;
      }
    }

    state.rows.sort((a, b) =>
      a.created_at.localeCompare(b.created_at) || a.id.localeCompare(b.id)
    );

    state.cursor = response.next;
    state.finished = response.next === null;
    results();
    status("Page loaded. Decryption and search stayed in this browser.");
  } finally {
    identityText = undefined;
    decrypter = undefined;
    $("identity-file").value = "";
    state.busy = false;
    $("load").disabled = state.finished;
  }
}

async function initialize() {
  if (!age?.Encrypter || !age?.Decrypter) {
    throw new Error("The local encryption library did not load.");
  }

  state.bootstrap = await api("/api/bootstrap/");
  const kind = state.bootstrap.kind;
  $(kind).hidden = false;

  if (kind === "recruit") {
	const placeholder = node(
	  "option",
	  state.bootstrap.companies.length
	    ? "Choose a destination company"
	    : "No companies have been configured"
	);
	placeholder.value = "";
	placeholder.disabled = true;
	placeholder.selected = true;
	$("company").append(placeholder);

	for (const item of state.bootstrap.companies) {
	  const option = node("option", item.name);
	  option.value = item.id;
	  $("company").append(option);
	}

	$("company").disabled = state.bootstrap.companies.length === 0;

    $("company").addEventListener("change", renderRecipients);
    renderRecipients();

    document.querySelectorAll("[data-add]").forEach(item => {
      item.addEventListener("click", () => run(() => addEntry(item.dataset.add)));
    });

    $("submission").addEventListener("submit", event => {
      event.preventDefault();
      run(async () => {
        $("submit-button").disabled = true;
        try {
          const destination = company();
          const ids = [...$("recipients").querySelectorAll("input:checked")]
            .map(input => Number(input.value));

          if (!destination || ids.length < 1 || ids.length > 10) {
            throw new Error("Select a company and between 1 and 10 recipients.");
          }
          if (!$("verified").checked) {
            throw new Error("Verify recipient identities and fingerprints.");
          }

          const payload = readPayload();
          const encrypter = new age.Encrypter();

          for (const id of ids) {
            const recipient = destination.recipients.find(
              item => item.key_id === id
            );
            encrypter.addRecipient(recipient.public_key);
          }

          status("Encrypting locally.");
          const ciphertext = await encrypter.encrypt(JSON.stringify(payload));
          status("Uploading ciphertext only.");

          await api("/api/submit/", {
            company_id: destination.id,
            key_ids: ids,
            ciphertext: base64(ciphertext),
            encryption_format: "age-v1",
            payload_schema_version: 1
          });

          for (const section of Object.keys(definitions)) {
            $(section).replaceChildren();
          }
          $("verified").checked = false;

          await history();
          status("Encrypted submission received.");
        } finally {
          $("submit-button").disabled = false;
        }
      });
    });

    await history();
  } else {
    $("key-form").addEventListener("submit", event => {
      event.preventDefault();
      run(async () => {
        const publicKey = $("public-key").value.trim();

        if (!publicKey.startsWith("age1") || publicKey.length !== 62) {
          throw new Error("Enter only a native age public recipient key.");
        }

        const encrypter = new age.Encrypter();
        encrypter.addRecipient(publicKey);
        await encrypter.encrypt(new Uint8Array());

        const result = await api("/api/keys/", { public_key: publicKey });
        if (!result.active) {
          throw new Error("This key is retired. Publish a new key.");
        }
        location.reload();
      });
    });

    for (const key of state.bootstrap.keys) {
      const card = node("article");
      card.append(node(
        "p",
        `${key.public_key}; version ${key.version}; ` +
        (key.active ? "active" : "retired")
      ));

      if (key.active) {
        card.append(button("Retire for future submissions", async () => {
          await api(`/api/keys/${key.id}/retire/`, {});
          location.reload();
        }));
      }

      $("keys").append(card);
    }

    $("load").addEventListener("click", () => run(loadPage));
    $("clear").addEventListener("click", clearReview);
    $("search").addEventListener("input", results);
    results();
  }

  await contacts();
}

$("logout").addEventListener("submit", clearReview);
window.addEventListener("pagehide", clearReview);
window.addEventListener("pageshow", event => {
  if (event.persisted) location.reload();
});

run(initialize);
