# ossie-guard

🇬🇧 **English:** [README.md](README.md)

**[Apache Ossie](https://github.com/apache/ossie) semantik modelleri için dürüstlük ve güvenlik linter'ı.**

Apache Ossie (Open Semantic Interchange'in referans uygulaması) bir metriğin
*birden fazla lehçe* için SQL ifadesi taşımasına izin verir — ANSI, Snowflake,
BigQuery, Databricks — böylece aynı ölçü farklı veri ambarları arasında taşınır.
Ossie'nin kendi `validation/validate.py` dosyası her ifadenin **parse edilip
edilmediğini** kontrol eder. Bir metriği gerçekten güvenilir yapan iki şeyi ise
kontrol **etmez**:

1. **Lehçeler birbiriyle uyuşuyor mu?** ANSI'de `SUM(amount)` ama Snowflake'te
   `AVG(amount)` olan bir metrik kusursuz parse edilir ve sessizce her motorda
   farklı bir sayı döndürür. Şema doğrulaması bunu asla görmez.
2. **İfade saf ve tekrar-üretilebilir bir okuma mı?** `pg_read_file(...)` çağıran
   ya da `NOW()` / `RANDOM()`'a bağlı bir "metrik" de sorunsuz parse edilir — ama
   bu ya bir yan etkidir ya da tekrar-üretilemezdir.

`ossie-guard` ikisini de yakalayan katmandır. `validate.py`'nin **tamamlayıcısıdır**:
önce şema doğrulayıcısını, sonra `ossie-guard`'ı çalıştırın.

```console
$ ossie-guard model.yaml
```

```
ossie-guard 0.3.1 - model.yaml

  ERROR    AGGREGATE_DRIFT  -  revenue
           aggregate functions differ across dialects: ANSI_SQL=['SUM']; SNOWFLAKE=['AVG']
           at model.yaml:8

  WARNING  COLUMN_DRIFT  -  gross_sales
           referenced columns differ across dialects; not shared by all: ss_ext_sales_price, ss_sales_price
           at model.yaml:16

  WARNING  LITERAL_DRIFT  -  revenue_with_tax
           numeric constants differ across dialects: ANSI_SQL=['1.08']; SNOWFLAKE=['1.18']
           at model.yaml:24

  1 error, 2 warnings
```

*(Bu, [`tests/fixtures/drift.yaml`](tests/fixtures/drift.yaml) için aracın birebir
çıktısıdır — bu dosyadaki her örnek gerçek çıktıdır, maket değil.)*

## Kurulum

```console
pip install ossie-guard
```

Bağımlılıklar tam olarak Ossie'nin kendi bağımlılıkları: `pyyaml` ve `sqlglot`,
başka hiçbir şey.

## Kullanım

```console
ossie-guard model.yaml                      # insan-okunur rapor
ossie-guard models/*.yaml                   # tek koşuda birden fazla model
ossie-guard model.yaml --format json        # makine-okunur
ossie-guard model.yaml --format sarif       # GitHub code scanning için SARIF 2.1.0
ossie-guard model.yaml -o report.sarif      # stdout yerine dosyaya yaz
ossie-guard model.yaml --fail-level warning # uyarılar da başarısız yapar (varsayılan: error)
ossie-guard model.yaml --no-determinism     # bir kontrolü kapat
ossie-guard models/*.yaml --write-baseline .ossie-guard-baseline.json   # mevcut modelde benimseme
ossie-guard models/*.yaml --baseline .ossie-guard-baseline.json         # yalnız YENİ bulgularda başarısız
```

Çıkış kodu: temizse `0`, `--fail-level` eşiğinde veya üzerinde bir bulgu varsa
`1`, kullanım/dosya hatasında `2`. `--fail-level none` koşuyu hiç başarısız
yapmaz (yalnızca rapor istediğinizde işe yarar); `--strict` ve `--exit-zero`
sırasıyla `warning` ve `none` için kısayol olarak durur.

### GitHub Action (bulgular pull request üzerinde işaretlenir)

`ossie-guard` bir composite action olarak da gelir: modellerinizi tarar ve SARIF
raporunu **code scanning**'e yükler, böylece her bulgu ilgili ifadenin tam
satırında satır-içi görünür:

```yaml
# .github/workflows/semantic-model.yml
name: semantic-model
on: [push, pull_request]

permissions:
  contents: read
  security-events: write     # SARIF yüklemek için gerekli
  # actions: read            # ÖZEL (private) repolarda ek olarak gerekli

jobs:
  ossie-guard:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
      - uses: gulmezeren2-byte/ossie-guard@v0.3.1
        with:
          path: models          # bir dosya, bir dizin ya da birden fazla yol
          fail-level: error     # error | warning | note | none
```

Ossie'nin kendi doğrulayıcısından **sonra** çalıştırın; o farklı bir soruyu
yanıtlar:

```yaml
      - run: python validation/validate.py models/model.yaml   # parse ediliyor mu?
      - uses: gulmezeren2-byte/ossie-guard@v0.3.1              # uyuşuyor mu ve saf mı?
```

Düz adımları mı tercih ediyorsunuz? CLI de CI dostu:

```yaml
      - run: pip install ossie-guard
      - run: ossie-guard models/*.yaml
```

### pre-commit

```yaml
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/gulmezeren2-byte/ossie-guard
    rev: v0.3.1
    hooks:
      - id: ossie-guard
        files: ^models/.*\.ya?ml$      # kendi model dizininize daraltın
```

### Kütüphane olarak

```python
from ossie_guard import lint_file, Severity

findings = lint_file("model.yaml")
for f in findings:
    print(f"{f.severity.value} {f.code} {f.entity} (satır {f.line}) - {f.message}")

if any(f.severity is Severity.ERROR for f in findings):
    raise SystemExit(1)
```

## Neleri kontrol eder

| Kod | Önem | Ne anlama gelir |
|-----|------|-----------------|
| `AGGREGATE_DRIFT` | error | Bir metriğin lehçeleri arasında agregat sınıfı farklı (`SUM` vs `AVG`, `COUNT` vs `COUNT DISTINCT`). Neredeyse her zaman bir hatadır. |
| `UNSAFE_FUNCTION` | error | İfade yan-etkili bir fonksiyon çağırıyor (dosya/soket/kabuk/executor): `pg_read_file`, `dblink`, `xp_cmdshell`, `load_file`, `load_extension`, … |
| `COLUMN_DRIFT` | warning | Başvurulan sütun kümesi lehçeler arasında farklı — sıklıkla bir lehçeyi yanlış sütunda bırakan kopyala-yapıştır. |
| `LITERAL_DRIFT` | warning | **Aritmetikte** kullanılan bir sabit lehçeler arasında farklı (`* 1.08`'den `* 1.18`'e kaymış bir vergi oranı). |
| `PREDICATE_DRIFT` | warning | **Filtre koşulları** lehçeler arasında farklı — kaymış bir metin sabiti (`region = 'EU'` vs `'US'`) ya da operatör (`> 100` vs `>= 100`) hangi satırların sayıldığını değiştirir. |
| `NONDETERMINISTIC` | warning | İfade `NOW()`, `CURRENT_DATE`, `RANDOM()`, `UUID()` … kullanıyor — aynı koşu farklı sayılar döndürebilir. |
| `PARSE_ERROR` | info | Parse edilemeyen bir ifade; onun için derin kontroller atlandı. |

## Neyi yakalar — neyi yakala**maz**

`ossie-guard` kendi sınırları konusunda dürüsttür, çünkü fazla iddia eden bir
linter hiç olmamasından kötüdür.

**Kayma (drift) kontrolleri bir sezgiseldir, denklik kanıtlayıcısı değildir.**
Gerçek SQL denkliği karar verilemezdir ve çok-lehçeli ifadelerin tüm amacı meşru
şekilde farklı olmalarıdır (bir motorda `COALESCE`, diğerinde `NVL`). Bu yüzden
`ossie-guard` bilinçli olarak yalnızca bir *yapısal imzayı* karşılaştırır —
agregat sınıfları, başvurulan sütunlar, aritmetik sabitler ve filtre
predikatları — ve **iyi huylu lehçe yazımını yok sayar**. Somut olarak:

- ✅ `SUM` vs `AVG`, yanlış sütun, kaymış aritmetik sabit, `COUNT` vs
  `COUNT DISTINCT` ve kaymış bir filtre (metin sabiti ya da operatör) yakalanır.
- ✅ Yalnızca yazım/idiom farkı olan ifadeler **işaretlenmez**. Aşağıdakilerin
  hepsi **eşit** sayılır:

  | bir lehçe | diğeri | neden kayma değil |
  |---|---|---|
  | `AVG(COALESCE(price, 0))` | `AVG(NVL(price, 0))` | aynı imza, farklı yazım |
  | `SUM(CASE WHEN s = 1 THEN amt ELSE 0 END)` | `SUM(amt) FILTER (WHERE s = 1)` | aynı filtre, farklı yapı |
  | `SUM(CASE WHEN s = 1 THEN amt ELSE 0 END)` | `SUM(IF(s = 1, amt, 0))` | aynı filtre, BigQuery idiomu |
  | `is_active = TRUE` | `is_active = 1` | motorlar boolean'ı farklı yazar |
  | `amt > 100` | `100 < amt` | operandlar ters yazılmış |
  | `status IN (1, 2)` | `status IN (2, 1)` | `IN` listesinde sıra anlam taşımaz |
  | `DATE_FORMAT(d, '%Y-%m')` | `FORMAT_DATE('%Y-%m', d)` | format string bir filtre değildir |

  (Resmî `flights` ve `tpcds` örnek modellerine karşı doğrulandı: **sıfır bulgu**.)
- ⚠️ İmzayı aynı bırakan anlamsal bir farkı **yakalamaz** — anlamı değiştiren bir
  join granülerliği, farklı bir `GROUP BY` bağlamı ya da sütun/operatör/değerleri
  aynı olup boolean yapısı değişen bir filtre (`A AND B` vs `A OR B`). Bunlar bir
  insan ya da ampirik bir test gerektirir.

Hataları (error) yüksek güvenli, uyarıları (warning) "bir insan bakmalı" olarak
değerlendirin.

### Zaten bulgusu olan bir modelde benimseme

Bir kez koşun, halihazırda var olanı kaydedin ve CI'ın yalnızca **yeni** bulgularda
başarısız olmasını sağlayın:

```console
ossie-guard models/*.yaml --write-baseline .ossie-guard-baseline.json
git add .ossie-guard-baseline.json
```

```yaml
      - uses: gulmezeren2-byte/ossie-guard@v0.3.1
        with:
          path: models
          baseline: .ossie-guard-baseline.json
```

Baseline'a alınan bir bulgu satır numarası olmadan kimliklendirilir; yani modeli
yeniden biçimlendirmek onu geri getirmez. Artık oluşmayan kayıtlar raporlanır ki
dosya temizlenebilsin. Bu bir mandal (ratchet), sesi kapatma düğmesi değil.

## Nasıl doğrulanıyor

Düşük yanlış-pozitif iddia eden bir linter bunu kanıtlamalıdır. Her push'ta
şunlar koşar:

| Kontrol | Neyi kanıtlar |
|---------|---------------|
| **62 test**, Python 3.9 / 3.11 / 3.12 / 3.13 / 3.14 | kontroller desteklenen her sürümde aynı davranıyor |
| **Apache Ossie'nin kendi `flights` + `tpcds` örneklerinde sıfır bulgu** | geçerli, gerçek dünya modellerinde gürültü yapmıyor |
| **SARIF, resmî OASIS 2.1.0 şemasına karşı doğrulanıyor** (çevrimdışı olması için repoya gömülü — ayrıca CI'da bağımsız bir `check-jsonschema` geçişi) | GitHub'ın aldığı rapor gerçek SARIF, "muhtemelen geçerli" değil |
| **Composite action CI'da kendi üzerinde koşuyor** — rapor üretmeli, kayan bir modelde başarısız olmalı, temiz modelde geçmeli | action belgelendiği gibi çalışıyor, yalnızca teoride değil |

## Bu neden var

Kardeş kütüphanesi
**[readonly-sql-guard](https://github.com/gulmezeren2-byte/readonly-sql-guard)**
ile aynı yerden geliyor — buradaki yan-etkili fonksiyon kara listesi ondan
portlandı — ve
[erp-report-engine](https://github.com/gulmezeren2-byte/erp-report-engine)'den:
*"salt-okunur", "tekrar-üretilebilir" ve "her motorda aynı"* ifadelerinin bir
aracın **ölçtüğü** özellikler olması gerektiği inancından; bir modelin öne
sürdüğü sıfatlar değil. Semantik katman, yanlış bir sayının aşağıdaki her panoya
yayıldığı tek yerdir; "parse ediliyor mu"nun ötesine bakan bir kontrolü hak eder.

## Geliştirme

```console
pip install -e ".[dev]"     # pytest + jsonschema ekler (SARIF şema testi için)
python -m pytest -q
```

Paketin kendisi yalnızca `pyyaml` ve `sqlglot`'a bağlıdır; `[dev]` içindeki her
şey yalnızca test amaçlıdır.

## Lisans

Apache-2.0 — Apache Ossie ile aynı lisans, böylece onun yanında rahatça
durabilir. Resmî bir Apache projesi değildir; "Apache Ossie" birlikte
çalışabilirlik için referans verilmiştir.
