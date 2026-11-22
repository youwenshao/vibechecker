import { Document, Font, Link, Page, Text, View, pdf } from "@react-pdf/renderer";
import english from "../messages/en.json";

type Kit = {
  locale: string;
  title: string;
  meta: string;
  version: string;
  score: string;
  index: number;
  band: string;
  range: string;
  caution: string;
  flags: string[];
  flagsTitle: string;
  whyTitle: string;
  why: string;
  signalsTitle: string;
  signals: string[][];
  adviceTitle: string;
  advice: string;
  footer: string;
  method: string;
};

export function createKit(k: Kit) {
  const chinese = k.locale === "zh-HK";
  if (chinese)
    Font.register({ family: "Evidence HK", src: location.origin + "/fonts/evidence-hk.ttf" });
  const heading = { fontSize: 14, marginTop: 18, marginBottom: 5 };
  return pdf(
    <Document title={k.title} author="VibeChecker" language={k.locale}>
      <Page
        size="A4"
        style={{
          padding: 38,
          fontFamily: chinese ? "Evidence HK" : "Helvetica",
          fontSize: 11,
          color: "#171512",
          backgroundColor: "#FAF8F4",
        }}
      >
        <Text style={{ fontSize: 12 }}>vibechecker.</Text>
        <Text style={{ fontSize: 26, marginTop: 8 }}>{k.title}</Text>
        <Text>{k.meta}</Text>
        <Text>{k.version}</Text>
        <View style={{ backgroundColor: "#E9E6F2", padding: 12, marginTop: 12 }}>
          <Text>{k.score}</Text>
          <Text style={{ fontSize: 24 }}>
            {k.index} / 100 · {k.band}
          </Text>
          <Text>{k.range}</Text>
        </View>
        <Text style={{ marginTop: 8 }}>{k.caution}</Text>
        {chinese && <Text>{english.chrome.foot}</Text>}
        <Text style={heading}>{k.whyTitle}</Text>
        <Text>{k.why}</Text>
        <Text style={heading}>{k.signalsTitle}</Text>
        {k.signals.map(([name, value]) => (
          <View
            key={name}
            style={{
              flexDirection: "row",
              justifyContent: "space-between",
              borderBottomWidth: 0.5,
              borderColor: "#c6c0b5",
              paddingVertical: 2,
            }}
          >
            <Text>{name}</Text>
            <Text>{value}</Text>
          </View>
        ))}
        {k.flags.length > 0 && (
          <View>
            <Text style={heading}>{k.flagsTitle}</Text>
            {k.flags.map((flag) => (
              <Text key={flag}>{flag}</Text>
            ))}
          </View>
        )}
        <Text style={heading}>{k.adviceTitle}</Text>
        <Text>{k.advice}</Text>
        <View style={{ position: "absolute", left: 38, right: 38, bottom: 28 }}>
          <Link
            style={{ color: "#302b46" }}
            src={"https://vibechecker.io/" + k.locale + "/methodology#lenses"}
          >
            {k.method}
          </Link>
          <Text>{k.footer}</Text>
        </View>
      </Page>
    </Document>,
  ).toBlob();
}
