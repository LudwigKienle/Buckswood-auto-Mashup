# Mashup-Komposition: Form, Erwartung und musikalischer Zusammenhang

Recherche und Umsetzung: 18. September 2026. Ziel: Buckswood auto Mashup mit vorhandenen lokalen Werkzeugen verbessern, ohne weitere kostenpflichtige APIs.

## Ergebnis der Recherche

Ein überzeugender Mashup braucht mehr als passende BPM, Tonarten und saubere Stems. Er muss Beziehungen zwischen musikalischen Ereignissen herstellen: Was wird vorgestellt? Was bleibt erkennbar? Was verändert sich? Worauf bereitet eine Passage vor? Wann ist ein Gedanke abgeschlossen?

Es gibt keine belastbare universelle „Mozart-/Mahler-Formel“. Klassische Satzregeln beschreiben bestimmte Stile; Experimente zur Musikwahrnehmung messen bestimmte Hörergruppen und Aufgaben. Beides ist nützlich, wenn der Geltungsbereich erhalten bleibt. Unser Ziel ist eine nachvollziehbare Auswahl guter musikalischer Möglichkeiten, keine automatische Garantie außergewöhnlicher Kunst.

**Kennzeichnung:** „Befund“ bezeichnet Aussagen der verlinkten Quelle. „Übertragung“ ist unsere eigene Anwendung auf Mashups. „Implementiert“ bezeichnet tatsächlich vorhandenen Code; Forschungsoptionen sind keine fertigen Funktionen. Zahlenwerte unserer Bewertungsfunktionen sind unkalibrierte Heuristiken.

## 1. Formale Funktion statt bloßer Taktzahl

**Befund:** Caplins Formenlehre unterscheidet unter anderem Präsentation, Fortsetzung und Kadenz sowie Vordersatz und Nachsatz. Eine Passage hat eine Funktion im Verlauf, nicht nur eine Länge. Sein eigener Lehrtext warnt davor, Analyse auf das Finden passender Etiketten zu reduzieren. Die Kategorien beziehen sich auf klassische Formbildung, insbesondere das Repertoire von Haydn, Mozart und Beethoven. [Caplin: Teaching Classical Form](https://www.music.mcgill.ca/~caplin/teaching-classical-form.pdf), [Classical Form, Oxford](https://academic.oup.com/book/49159).

**Übertragung:** Ein Sängerwechsel nach acht Takten kann falsch sein, wenn die musikalische Aussage noch auf ihre Antwort wartet. Intro, Thema und Rückkehr sollten unterschiedliche Aufgaben erfüllen. Ein SheetSage-Label „chorus“ alleine macht einen Ausschnitt weder zum guten Einstieg noch zum richtigen Drop.

**Implementiert:** Ganze zusammenhängende Passagen und geschätzte Strukturgrenzen haben Vorrang vor einer erzwungenen Drei-Minuten-Länge. Echte formfunktionale oder kadenzielle Analyse ist noch nicht implementiert.

## 2. Wiederholung muss Erinnerung ermöglichen; Variation muss Beziehung bewahren

**Befund:** Schönberg beschreibt in „My Evolution“ die Entwicklung seiner kompositorischen Mittel und die Verbindung von thematischer Arbeit und größeren Formen. Die historische Perspektive erklärt einen Arbeitsansatz, sie beweist keine allgemeingültige Qualitätsfunktion. [Schönbergs eigener Vortrag](https://schoenberg.at/en?id=965%3Avr01&option=com_content&view=article).

**Übertragung:** Für einen Mashup bietet sich A → B → A′ an: Erst eine Identität etablieren, dann antworten, schließlich das Bekannte in verändertem Kontext zurückbringen. Ständig völlig neue Ausschnitte verbrauchen Aufmerksamkeit, bevor sich Wiedererkennung einstellen kann. Umgekehrt wird unverändertes Wiederholen nicht allein durch größere Lautstärke zur Entwicklung.

**Implementiert:** Thema A kehrt im Drop zurück. Eine Suche nach musikalisch verwandten Varianten A′ statt der identischen Passage ist ein nächster Forschungsschritt.

## 3. Mahler: Rückkehr kann eine veränderte Bedeutung tragen

**Befund:** Lew Smoleys Analyse von Mahlers Fünfter beschreibt die Transformation wiederkehrender Themen über Satzgrenzen hinweg. Sie behandelt zugleich abrupte Unterbrechungen und starke Kontraste als Bestandteile der Dramaturgie. Das widerspricht einem pauschalen Verbot harter Wechsel. [Mahler Foundation: Fünfte Symphonie](https://www.mahlerfoundation.net/mahler/listening-guide/listening-guide-symphony-no-5-intro/).

**Übertragung:** Ein harter Cut darf als vorbereiteter Höhepunkt funktionieren. Problematisch ist der unbegründete Cut. Unser Standard sollte Zusammenhang bevorzugen, während ein späterer ausdrücklich gewählter Kontrastmodus stärkere Brüche erlauben könnte. „Klingt wie Mahler“ ist weder Zielmetrik noch durch diese Regeln gewährleistet.

## 4. Ein musikalischer Zusammenhang kann mehrere Rückläufe umfassen

**Befund:** Ji Yeon Lees Wagner-Analyse untersucht rotierende Motivfolgen, die bei ihrem Wiederkehren verändert werden und eine dramatische Entwicklung tragen. Das ist eine konkrete analytische Interpretation einer Szene, keine experimentell bestätigte Anleitung für Pop. [Music Theory Online, 2022](https://www.mtosmt.org/issues/mto.22.28.2/mto.22.28.2.lee.html).

**Übertragung:** Wiedererkennbare Reihenfolgen können einen längeren Mashup tragen: Motiv → Antwort → Rückkehr, später mit anderer Dichte oder Begleitung. Für drei Minuten genügen oft wenige klar entwickelte Ideen. Mehr Material ist nicht automatisch mehr Entwicklung.

## 5. Übergänge benötigen eine Verbindung zwischen Ausgang und Ziel

**Befund:** Alan Belkin behandelt harmonische Übergänge als graduell oder abrupt; die Stärke des Kontrasts soll zur jeweiligen Formstelle passen. Bei allmählichen Übergängen können gemeinsame Elemente und schrittweise eingeführte neue Töne den Zusammenhang erhalten. [Belkin: Movement, Interest, and Variety](https://alanbelkinmusic.com/general-principles-of-harmony-movement-interest-and-variety/).

**Übertragung:** Beim Sängerwechsel bleibt zunächst dieselbe Begleitung. Erst danach darf deren harmonische Identität wechseln. Das ist unsere praktikable Regel zur Verteilung von Aufmerksamkeit, kein von Belkin vorgeschriebenes Mashup-Gesetz.

**Implementiert:** Der spätere Begleitungswechsel wird nun unter mehreren Taktgrenzen verglichen: bei 24 Takten nach 8 oder 16; bei 32 nach 8, 16 oder 24. Der Gesang läuft dabei unverändert weiter. Gesangsaktivität am Wechsel, harmonischer Anschluss und interne Klangwechsel der tatsächlich verwendeten Begleitungen beeinflussen die Entscheidung.

## 6. Stimmführung ist nicht dasselbe wie globale Tonart

**Befund:** Hurons Forschungsdarstellung verbindet Stimmführung mit auditiver Wahrnehmung, der Verfolgbarkeit einzelner Stimmen und deren Zusammenspiel. Das erklärt, warum bloß gleichzeitig erklingende korrekte Tonklassen noch keine überzeugende Textur garantieren. [Huron: Voice Leading, MIT Press](https://mitpress.mit.edu/9780262537384/voice-leading/).

**Übertragung:** Gemeinsame Töne können einen Instrumentalwechsel verbinden. Eine globale Camelot-Kompatibilität ersetzt weder die Prüfung konkreter Melodietöne über konkreten Akkorden noch die Behandlung konkurrierender Melodien.

**Implementiert:** Akustische Chromavektoren werden zeitlich verglichen. Neu kommt ein weicher Vergleich des harmonischen Materials unmittelbar vor/nach dem Instrumentalwechsel hinzu. Das ist ausdrücklich **keine echte Stimmführungsanalyse**: Register, einzelne Stimmen, Vorhalte und ihre Auflösung fehlen. Stille/fehlende Toninformation wird nicht als Dissonanz bestraft. Funktionierende Akkordwechsel sollen möglich bleiben, deshalb ist dieser Kostenanteil klein.

## 7. Überraschung hängt vom aufgebauten Kontext ab

**Befund:** Cheung und Kollegen zeigen einen nichtlinearen Zusammenhang zwischen musikalischem Gefallen, vorheriger Unsicherheit und Überraschung. Daraus folgt keine simple Regel „mehr Überraschung ist besser“, und auch kein optimaler universeller Prozentwert. [Originalpublikation und Abstract, Cambridge](https://cms.mus.cam.ac.uk/publications/cheung-uncertainty-surprise/).

**Übertragung:** Ein unerwarteter Sänger auf vertrauter Begleitung kann verständlicher wirken als ein gleichzeitiger Wechsel von Stimme, Harmonie, Groove und Lautheit. Ein späterer Planer könnte mehrere Neuheitsdimensionen getrennt messen und starke Veränderungen gezielt an wenige Formstellen legen. Ein solcher Erwartungsmodell- oder Neuroästhetik-Score ist derzeit nicht implementiert.

## 8. Phrasen sind hörbare Einheiten, kein starres Raster

**Befund:** Native Instruments beschreibt Phrase Mixing anhand zusammengehöriger Abschnitte, deren Anfänge und Enden aufeinander abgestimmt werden. Acht oder sechzehn Takte sind verbreitete Größen, können aber abweichen. Der Leitfaden unterscheidet unter anderem Intro, Verse, Breakdown/Build und Chorus/Drop. [Phrase Mixing](https://blog.native-instruments.com/phrase-mixing/).

**Übertragung:** Taktanfänge liefern das metrische Gerüst; Pausen, vollständige Gesangsgesten und Strukturhinweise liefern zusätzliche Grenzen. Auch ein Auftakt vor der Eins gehört zur Phrase. Texte lassen sich nicht zuverlässig aus Lautstärke ableiten.

**Implementiert:** Bestehender Schutz für Auftakte und Wortenden bleibt erhalten. Neu unterscheidet der Planer gleich hohe durchschnittliche Gesangsaktivität mit flüssigem Verlauf von verspäteten Einsätzen oder großen internen Lücken. Normale Atempausen werden toleriert; Ausklang nach dem letzten aktiven Gesang zählt nicht als interne Lücke. Instrumentalabschnitte sind von dieser Vocal-Bewertung nicht betroffen.

## 9. Realistische Rhythmusorganisation statt beliebiger Übergangslängen

**Befund:** Die Untersuchung realer DJ-Mixe von Kim und Kollegen findet Häufungen von Übergangslängen in Vielfachen von 32 Beats. Sie zeigt zugleich, dass Übergangsgrenzen selbst für Menschen mehrdeutig sind. Das betrifft DJ-Mixe und ist nicht unmittelbar ein Ergebnis über vollständige Vocal-Mashups. [ISMIR 2020: Mix-To-Track Alignment](https://arxiv.org/html/2008.10267).

**Übertragung:** Unsere 8-Takt-Kandidaten sind ein sinnvoller Suchraum für 4/4-Material. Sie sind keine Garantie für die tatsächliche Phrasenphase. Eine Acht-Takt-Passage, die mitten im Motiv beginnt, bleibt musikalisch problematisch. Ungewöhnliche Metren und falsch erkannte Halb-/Doppeltempi benötigen zusätzliche Prüfung.

## 10. Die Rollen der Songs sind entscheidend

**Befund:** AutoMashup 2025 untersucht gerichtete Kombinationen von Vocals und Begleitung. A über B ist nicht mit B über A gleichzusetzen. Die Autoren berichten Grenzen allgemeiner CLAP-/MERT-Ähnlichkeiten als Ersatz für passende Kombinationen. Ihre Auswahlstudie umfasst nur 21 bewusst eingeschränkte Songs. Die Eignung von COCOLA für Gesangs-Mashups wird dort als empirische Beobachtung, nicht als formell validierter allgemeiner Hörtest dargestellt. [AutoMashup-Paper](https://arxiv.org/html/2508.06516v1), [Originalcode](https://github.com/ax-le/automashup).

**Übertragung:** Beide tatsächlich verwendeten Richtungen prüfen. Gute Vorwärtskompatibilität darf eine schwache Antwort nicht verstecken. Keine Genre-/Mood-API als Ersatz für den musikalischen Vergleich kaufen.

**Implementiert:** Beide Richtungen werden weiterhin separat bewertet; bei jeder möglichen Begleitungsübergabe wird die tatsächlich verbleibende B-über-A-Passage geprüft.

## 11. Klangschonende Transformation ist Teil der Komposition

**Befund:** Huang und Kollegen begrenzen ihre Kandidatensuche unter anderem nach Transposition und Temporatio, um Transformationsartefakte zu reduzieren. Die dortigen Grenzwerte sind Entscheidungen dieser Forschungspipeline, keine sicheren Hörschwellen. [AAAI 2021: Stem Compatibility](https://arxiv.org/html/2103.14208).

**Übertragung:** Eine theoretisch etwas bessere Tonpassung rechtfertigt nicht jede Verformung einer Stimme. Nicht nur das mittlere Songtempo, sondern die tatsächlich ausgewählten Takte müssen zur Zielgeschwindigkeit passen.

**Implementiert:** Starke Pitch-Shifts hatten bereits höhere Kosten. Neu werden lokale Taktlängen gegen das Zieltempo bewertet, mit gleicher Behandlung reziproker Geschwindigkeitsänderungen. Der Vorschlag für das gemeinsame Tempo bleibt das geometrische Mittel der geschätzten Quelltempi, begrenzt auf den unterstützten Bereich. Es ist ein Kompromiss und keine Garantie natürlicher Vocals.

Die Oberfläche hält Auto-Tempo nun als Automatik aktiv; ein Songwechsel verwirft das Tempo des vorigen Paars. Manuelle BPM bleiben innerhalb des gewählten Paars möglich. Der Renderer erhält genau das angezeigte Zieltempo.

## 12. Spannungskurve heißt nicht einfach Lautstärkekurve

**Befund:** Belkin unterscheidet gerichtete Entwicklungen und Höhepunkte in mehreren musikalischen Dimensionen. Die richtige Realisierung hängt vom vorhandenen Material ab, nicht von einer universellen Formschablone. [Lehrhinweise des Autors](https://www.alanbelkinmusic.com/PDF/InstructorSuggestions.pdf), [Einführung des Autors](https://alanbelkinmusic.com/PDF/Musical_composition-Introduction.pdf).

**Übertragung:** Ein Drop kann durch das Ende einer Verdichtung, die Rückkehr des Basses, den Abschluss einer harmonischen Spannung oder das Wiedererkennen des Hooks wirken. Ein dauerhaft volles Instrumental mit bloßem Lautheitsanstieg hat weniger Kontrastreserven.

**Implementiert:** Das verbundene Intro berücksichtigt jetzt die Energie der harmonischen Begleitung und deren Klangwechsel, auch wenn dort kaum Drums spielen. Bass-/Drum-Aufbau und anschließender kontinuierlicher Stem-Verlauf bleiben erhalten. Eine zuverlässige Kadenz- und Spannungsanalyse wird damit noch nicht behauptet.

## Beispiel für eine eigene Formidee

Dies ist eine von uns entworfene Arbeitsform, keine rekonstruierte Kompositionstechnik Mozarts oder Mahlers. Bei 120 BPM dauern 88 Takte 2:56 Minuten:

| Takte | Funktion | Gedanke |
|---|---|---|
| 1–8 | Intro | Motiv der folgenden Begleitung vorstellen; Rhythmus allmählich öffnen |
| 9–32 | Thema A | Eine erkennbare, vollständige Aussage auf Begleitung B |
| 33–40 | Antwort B | Neue Stimme, zunächst vertraute Begleitung B |
| 41–56 | Weiterführung B | Stimme bleibt kontinuierlich; passende Harmonie aus A übernimmt |
| 57–60 | Vorbereitung | Dichte zurücknehmen bzw. Erwartung bündeln |
| 61–84 | Rückkehr A | Bekanntes Motiv trägt den Höhepunkt |
| 85–88 | Schluss | Material reduzieren, hörbaren Abschluss ermöglichen |

Je nach Quellmaterial können Intro, Themen und Übergabepunkt anders ausfallen. Ein ausklingender Klang ist noch keine Kadenz; ein wiederholter Hook noch keine entwickelte Reprise. Deshalb sind Formlabels eine Beschreibung der beabsichtigten Aufgabe, nicht der Beweis ihrer Wirkung.

## Technische Umsetzung dieser Iteration

| Veränderung | Messbare Prüfung | Grenze |
|---|---|---|
| Variable Begleitungsübergabe | Synthetische Harmonieänderung verschiebt Übergabe von Takt 8 nach 16; Vocal-Zeitachse bleibt identisch | Chroma-Nähe ist keine vollständige Harmonielehre |
| Lokale Tempokosten | Gleiche mittlere Taktlänge, aber stärkere lokale Verformung erhält höhere Kosten | Beat-Tracking kann irren |
| Gesangsverlauf | Gleich hohe Aktivität mit langen Lücken wird schlechter bewertet | Kein Sprach-/Satzverständnis |
| Intro aus tatsächlicher Begleitung | Drumloser harmonischer Aufbau beeinflusst Introauswahl | Kein automatischer Nachweis eines guten Hooks |
| Auto-Tempo | Songwechsel setzt alten Wert zurück; Planung fixiert Automatik nicht versehentlich | Weit auseinanderliegende Songs können weiterhin schlecht passen |

Die neuen Größen werden im Planungsergebnis dokumentiert. Bestehende Audio-, Phrase-, Struktur-, Dauer- und API-Tests bleiben relevant. Ein bestandener Test belegt Verhalten und Signal-Invarianten, keine ästhetische Überlegenheit.

## Nächste Forschungsschritte nach dieser Iteration

1. **Echter Vergleich vorher/nachher:** identische Stems und Master-Lautheit; anonymisierte Ausschnitte für Intro, Sängerwechsel und Begleitungswechsel. Getrennt bewerten: Natürlichkeit, harmonische Passung, Zusammenhang, Spannung und Textverständlichkeit. Keine Gesamtzahl aus einem einzigen Beispiel ableiten.
2. **Formfunktionen vorsichtig annähern:** Akkordverlauf, Bassbewegung, melodische Schlussgeste und Pause gemeinsam prüfen. Keine Kadenz aus einem Tonartlabel erfinden. Bei geringer Evidenz die vorhandene Quellphrase erhalten.
3. **Motivähnlichkeit und A′:** Wiederholte Passagen desselben Songs suchen, die ihre Identität behalten, aber unterschiedliche Dichte besitzen. Anschließend mehrere Formvarianten vergleichen, statt nur Startzeiten zu optimieren.
4. **Spezialisierter lokaler Kompatibilitätsvergleich:** COCOLA ist als Forschungsbaustein interessant; es misst Aspekte musikalischer Kohärenz, nicht die komplette Dramaturgie eines dreiminütigen Songs. Erst Eignung für Vocals, Modelllizenz, Rechenbedarf und Hörtest-Korrelation klären. [Paper](https://arxiv.org/html/2404.16969v4), [offizielles Repository](https://github.com/gladia-research-group/cocola). Nicht in dieser Iteration installiert.
5. **Alternative Strukturanalyse als Vergleich:** All-In-One liefert unter anderem Beats und gelabelte Struktursegmente. Es kann SheetSage ergänzen, muss aber zunächst gegen die vorhandenen Analysen verglichen werden. Mehr Modelle sind nicht automatisch bessere Entscheidungen. [Offizielles Repository](https://github.com/mir-aidj/all-in-one). Nicht neu installiert.

Keine neuen kostenpflichtigen Aufrufe, keine hochgeladenen Songs und keine neuen Modell-Downloads sind für diese Änderungen erforderlich. Bereits lokal gespeicherte LALAL-Stems bleiben als Quelle nutzbar.

## Zusätzlich behobener Fehler: lokal regelmäßige Musik wurde verworfen

Während der Arbeit trat beim tatsächlichen Songpaar die Meldung „Zu wenige zusammenhängende Takte mit Gesang“ auf. Ursache war ein globaler Vergleich aller Taktlängen: Gleichmäßige Passagen mit abweichendem lokalem Tempo wurden pauschal ausgeschlossen. Die Prüfung verwendet jetzt ein lokales Medianfenster und zählt die erkannten Beats zwischen den Taktmarkern. Sie verschiebt keine Marker und erfindet keine fehlenden Beats. Abschnitte mit ausgelassenen/doppelten Takten oder ohne vier erkannte Beats bleiben ausgeschlossen. Synthetische Regressionstests prüfen beide Fälle. Das ist eine Korrektur der Auswahl, kein Beweis für die wahre Taktart eines Songs.
