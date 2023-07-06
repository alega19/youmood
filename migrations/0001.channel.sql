CREATE TABLE "channel" (
    "id" text NOT NULL,
    "added" timestamptz NOT NULL,
    "title" text,
    "num_subscribers" int8,
    "synchronized" timestamptz,
    "angry" real,
    "happy" real,
    "sad" real,
    "surprise" real,
    "fear" real,
    "disgust" real,
    "neutral" real,
    "contempt" real,
    CONSTRAINT "channel_pk" PRIMARY KEY ("id"),
    CONSTRAINT "channel_id_non_empty" CHECK (length("id") > 0),
    CONSTRAINT "channel_num_subscribers_non_negative" CHECK ("num_subscribers" >= 0)
);
