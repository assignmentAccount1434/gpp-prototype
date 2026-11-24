const encoder = new TextEncoder();

function object(value, allowed, required) {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error("Expected a structured object.");
  }
  if (Object.keys(value).some(key => !allowed.includes(key))) {
    throw new Error("An unsupported field was included.");
  }
  if (required.some(key => !Object.hasOwn(value, key))) {
    throw new Error("A required field is missing.");
  }
}

function text(value, maximum, optional = false) {
  if (optional && value === undefined) return;
  if (
    typeof value !== "string" ||
    !value.trim() ||
    value.length > maximum
  ) {
    throw new Error("A text field is empty or too long.");
  }
}

export function validatePayload(payload) {
  object(
    payload,
    ["schema_version", "experience", "education", "skills"],
    ["schema_version", "experience", "education", "skills"]
  );

  if (payload.schema_version !== 1) {
    throw new Error("Unsupported payload schema.");
  }

  for (const section of ["experience", "education", "skills"]) {
    if (!Array.isArray(payload[section]) || payload[section].length > 50) {
      throw new Error("Each section supports at most 50 entries.");
    }
  }

  if (
    payload.experience.length +
    payload.education.length +
    payload.skills.length === 0
  ) {
    throw new Error("Include at least one experience, education, or skill.");
  }

  for (const entry of payload.experience) {
    const fields = [
      "role", "duration_months", "responsibilities", "accomplishments"
    ];
    object(entry, fields, fields);
    text(entry.role, 120);
    text(entry.responsibilities, 2000);
    text(entry.accomplishments, 2000);

    if (
      !Number.isInteger(entry.duration_months) ||
      entry.duration_months < 0 ||
      entry.duration_months > 1200
    ) {
      throw new Error("Duration must be an integer from 0 to 1200 months.");
    }
  }

  for (const entry of payload.education) {
    object(
      entry, ["qualification", "subject"], ["qualification", "subject"]
    );
    text(entry.qualification, 120);
    text(entry.subject, 120);
  }

  for (const entry of payload.skills) {
    object(entry, ["name", "proficiency", "evidence"], ["name"]);
    text(entry.name, 100);
    text(entry.proficiency, 100, true);
    text(entry.evidence, 1000, true);
  }

  if (encoder.encode(JSON.stringify(payload)).length > 100_000) {
    throw new Error("The structured submission is too large.");
  }

  return payload;
}

export function searchLoaded(rows, query) {
  const keywords = query.toLowerCase().trim().split(/\s+/).filter(Boolean);

  return rows.filter(({ payload }) => {
    const index = [
      ...payload.experience.flatMap(entry => [
        entry.role,
        entry.responsibilities,
        entry.accomplishments
      ]),
      ...payload.skills.map(entry => entry.name)
    ].join(" ").toLowerCase();

    return keywords.every(keyword => index.includes(keyword));
  });
}
