import {useEffect, useMemo, useRef, useState} from "react";
import {Alert, Box, Card, CardContent, CircularProgress, Stack, Switch, TextField, Typography} from "@mui/material";
import InfoOutlinedIcon from "@mui/icons-material/InfoOutlined";
import {Document, Page, pdfjs} from "react-pdf";
import "react-pdf/dist/Page/TextLayer.css";
import "react-pdf/dist/Page/AnnotationLayer.css";
import {type GuidelineEntry, type GuidelineReference, type GuidelineReferenceType, useReferenceApi} from "../../api/references";
import {normalizeObjectId} from "../../api/system";

pdfjs.GlobalWorkerOptions.workerSrc = new URL("pdfjs-dist/build/pdf.worker.min.mjs", import.meta.url).toString();

const pdfObjectUrlCache = new Map<string, string>();
const PDF_PAGE_RATIO = 1.4142;

type Props = {
  guidelineId: string;
  guideline: GuidelineEntry | null;
  references?: GuidelineReference[];
  selectedReferenceId?: string | null;
  onSelect?: (referenceId: string) => void;
  showHeader?: boolean;
  showReferenceToggle?: boolean;
  framed?: boolean;
};

type OverlayBox = {
  key: string;
  referenceId: string;
  referenceType: GuidelineReferenceType;
  pageNumber: number;
  left: number;
  top: number;
  width: number;
  height: number;
};

type PageSize = {
  width: number;
  height: number;
};

const REFERENCE_TYPE_COLORS: Record<GuidelineReferenceType, string> = {
  recommendation: "#8BC34A",
  statement: "#4aa60c",
  text: "#1E88E5",
  metadata: "#e87f15",
  table: "#159191",
  image: "#2ddada",
};

function asNumber(value: unknown): number | null {
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
}

function getReferenceId(reference: GuidelineReference): string | null {
  return normalizeObjectId((reference as any)?._id);
}

function flattenReferenceBoxes(references: GuidelineReference[] = []): OverlayBox[] {
  const rawBoxes: OverlayBox[] = [];

  for (const reference of references) {
    const referenceId = getReferenceId(reference);
    if (!referenceId) continue;

    const bboxList = Array.isArray((reference as any)?.bboxs)
      ? (reference as any).bboxs
      : Array.isArray((reference as any)?.bboxes)
        ? (reference as any).bboxes
        : [];

    bboxList.forEach((bbox: any, bboxIndex: number) => {
      const positions = Array.isArray(bbox?.positions) ? bbox.positions : null;
      if (!positions || positions.length < 4) return;

      const left = asNumber(positions[0]);
      const top = asNumber(positions[1]);
      const right = asNumber(positions[2]);
      const bottom = asNumber(positions[3]);
      const rawPage = asNumber(bbox?.page);

      if (left === null || top === null || right === null || bottom === null || rawPage === null) {
        return;
      }

      const width = right - left;
      const height = bottom - top;
      if (width <= 0 || height <= 0) return;

      rawBoxes.push({
        key: `${referenceId}-${bboxIndex}`,
        referenceId,
        referenceType: reference.type,
        pageNumber: Math.max(1, rawPage),
        left,
        top,
        width,
        height,
      });
    });
  }

  return rawBoxes;
}

function getRenderedBoxStyle(box: OverlayBox, pdfPageSize: PageSize, renderedPageSize: PageSize) {
  if (
    pdfPageSize.width <= 0 ||
    pdfPageSize.height <= 0 ||
    renderedPageSize.width <= 0 ||
    renderedPageSize.height <= 0
  ) {
    return null;
  }

  const left = (box.left / pdfPageSize.width) * renderedPageSize.width;
  const top = (box.top / pdfPageSize.height) * renderedPageSize.height;
  const width = (box.width / pdfPageSize.width) * renderedPageSize.width;
  const height = (box.height / pdfPageSize.height) * renderedPageSize.height;

  return {left, top, width, height};
}

function PdfPageWithOverlay(props: {
  pageNumber: number;
  pageWidth: number;
  boxes: OverlayBox[];
  showReferences: boolean;
  selectedReferenceId?: string | null;
  onSelect?: (referenceId: string) => void;
}) {
  const {pageNumber, pageWidth, boxes, showReferences, selectedReferenceId, onSelect} = props;
  const pageRef = useRef<HTMLDivElement | null>(null);
  const [renderedPageSize, setRenderedPageSize] = useState<PageSize>({width: 0, height: 0});
  const [pdfPageSize, setPdfPageSize] = useState<PageSize>({width: 0, height: 0});

  useEffect(() => {
    if (!pageRef.current) return;

    const updateSize = () => {
      if (!pageRef.current) return;
      const rect = pageRef.current.getBoundingClientRect();
      setRenderedPageSize({width: rect.width, height: rect.height});
    };

    updateSize();

    const observer = new ResizeObserver(() => updateSize());
    observer.observe(pageRef.current);

    return () => observer.disconnect();
  }, [pageWidth]);

  return (
    <Box sx={{display: "flex", justifyContent: "center", mb: 2}}>
      <div style={{position: "relative", width: pageWidth, maxWidth: "100%"}}>
        <Page
          pageNumber={pageNumber}
          width={pageWidth}
          inputRef={pageRef}
          renderTextLayer
          renderAnnotationLayer
          onLoadSuccess={(page: any) => {
            const viewport = page.getViewport({scale: 1});
            setPdfPageSize({width: viewport.width, height: viewport.height});
          }}
          onRenderSuccess={() => {
            if (!pageRef.current) return;
            const rect = pageRef.current.getBoundingClientRect();
            setRenderedPageSize({width: rect.width, height: rect.height});
          }}
          loading={<CircularProgress size={24} />}
        />

        {showReferences ? (
          <div style={{position: "absolute", inset: 0, pointerEvents: "none"}}>
            {boxes.map((box) => {
              const style = getRenderedBoxStyle(box, pdfPageSize, renderedPageSize);
              if (!style) return null;

              const isSelected = box.referenceId === selectedReferenceId;
              const highlightColor = REFERENCE_TYPE_COLORS[box.referenceType];

              return (
                <button
                  key={box.key}
                  type="button"
                  onClick={(event) => {
                    event.preventDefault();
                    event.stopPropagation();
                    onSelect?.(box.referenceId);
                  }}
                  style={{
                    position: "absolute",
                    left: style.left,
                    top: style.top,
                    width: Math.max(2, style.width),
                    height: Math.max(2, style.height),
                    borderRadius: 5,
                    border: isSelected ? `1.5px solid ${highlightColor}` : "none",
                    backgroundColor: isSelected ? `${highlightColor}5C` : `${highlightColor}26`,
                    boxShadow: isSelected ? `inset 0 0 0 1px ${highlightColor}` : "none",
                    boxSizing: "border-box",
                    cursor: "pointer",
                    padding: 0,
                    zIndex: 2,
                    pointerEvents: "auto",
                    appearance: "none",
                    WebkitAppearance: "none",
                  }}
                  data-reference-id={box.referenceId}
                  aria-label={`Reference highlight ${box.referenceId}`}
                />
              );
            })}
          </div>
        ) : null}
      </div>
    </Box>
  );
}

export default function ReferencePdfPanel(props: Props) {
  const {
    guidelineId,
    guideline,
    references = [],
    selectedReferenceId = null,
    onSelect,
    showHeader = true,
    showReferenceToggle = true,
    framed = true,
  } = props;

  const {fetchGuidelinePdfBlob} = useReferenceApi();
  const fetchPdfRef = useRef(fetchGuidelinePdfBlob);
  const scrollAreaRef = useRef<HTMLDivElement | null>(null);

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pdfUrl, setPdfUrl] = useState<string | null>(null);
  const [numPages, setNumPages] = useState(0);
  const [pageWidth, setPageWidth] = useState(900);
  const [currentPage, setCurrentPage] = useState(1);
  const [pageInput, setPageInput] = useState("1");
  const [showReferences, setShowReferences] = useState(true);

  const overlayBoxes = useMemo(() => flattenReferenceBoxes(references), [references]);
  const boxesByPage = useMemo(() => {
    const grouped = new Map<number, OverlayBox[]>();
    for (const box of overlayBoxes) {
      const current = grouped.get(box.pageNumber) ?? [];
      current.push(box);
      grouped.set(box.pageNumber, current);
    }
    return grouped;
  }, [overlayBoxes]);

  const guidelineLabel = useMemo(
    () => guideline?.title ?? (guideline as any)?.short_title ?? guideline?.awmf_register_number ?? guidelineId,
    [guideline, guidelineId],
  );

  const scrollToPage = (pageNumber: number) => {
    const nextPage = Math.min(Math.max(1, pageNumber), Math.max(1, numPages));
    const element = scrollAreaRef.current?.querySelector<HTMLDivElement>(`[data-page-number="${nextPage}"]`);
    if (!element) return;

    element.scrollIntoView({
      behavior: "smooth",
      block: "start",
      inline: "nearest",
    });

    setCurrentPage(nextPage);
    setPageInput(String(nextPage));
  };

  const handlePageJump = () => {
    const requestedPage = Number(pageInput);
    if (!Number.isFinite(requestedPage)) {
      setPageInput(String(currentPage));
      return;
    }

    scrollToPage(requestedPage);
  };

  useEffect(() => {
    fetchPdfRef.current = fetchGuidelinePdfBlob;
  }, [fetchGuidelinePdfBlob]);

  useEffect(() => {
    const updateSize = () => {
      if (!scrollAreaRef.current) return;
      const nextWidth = Math.max(280, Math.floor(scrollAreaRef.current.clientWidth - 24));
      setPageWidth(nextWidth);
    };

    updateSize();

    if (!scrollAreaRef.current) return;

    const observer = new ResizeObserver(() => updateSize());
    observer.observe(scrollAreaRef.current);

    return () => observer.disconnect();
  }, [pdfUrl]);

  useEffect(() => {
    let cancelled = false;

    async function loadPdf() {
      setLoading(true);
      setError(null);
      setPdfUrl(null);
      setNumPages(0);
      setCurrentPage(1);
      setPageInput("1");

      try {
        const cachedPdfUrl = pdfObjectUrlCache.get(guidelineId);
        if (cachedPdfUrl) {
          setPdfUrl(cachedPdfUrl);
          return;
        }

        const blob = await fetchPdfRef.current(guidelineId);
        if (cancelled) return;

        if (!(blob instanceof Blob) || blob.size === 0) {
          throw new Error("Could not load PDF.");
        }

        const objectUrl = URL.createObjectURL(
          blob.type === "application/pdf" ? blob : new Blob([blob], {type: "application/pdf"}),
        );

        pdfObjectUrlCache.set(guidelineId, objectUrl);
        setPdfUrl(objectUrl);
      } catch (error: any) {
        if (cancelled) return;
        setError(error?.message ?? "Could not load PDF.");
        setPdfUrl(null);
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    void loadPdf();

    return () => {
      cancelled = true;
    };
  }, [guidelineId]);

  useEffect(() => {
    if (!selectedReferenceId) return;

    const element = scrollAreaRef.current?.querySelector<HTMLButtonElement>(
      `[data-reference-id="${selectedReferenceId}"]`,
    );
    if (element) {
      element.scrollIntoView({
        behavior: "smooth",
        block: "center",
        inline: "nearest",
      });
    }

    const selectedReference = references.find((reference) => getReferenceId(reference) === selectedReferenceId);
    const selectedPage = selectedReference?.bboxs?.[0]?.page;
    if (typeof selectedPage === "number" && Number.isFinite(selectedPage)) {
      scrollToPage(selectedPage);
    }
  }, [numPages, overlayBoxes, references, selectedReferenceId]);

  useEffect(() => {
    if (!numPages) {
      setCurrentPage(1);
      setPageInput("1");
      return;
    }

    setCurrentPage((prev) => Math.min(Math.max(1, prev), numPages));
  }, [numPages]);

  useEffect(() => {
    const container = scrollAreaRef.current;
    if (!container || !numPages) return;

    const updateCurrentPage = () => {
      const pageElements = Array.from(container.querySelectorAll<HTMLElement>("[data-page-number]"));
      if (!pageElements.length) return;

      const containerRect = container.getBoundingClientRect();
      const viewportCenter = containerRect.top + containerRect.height / 2;

      let closestPage = 1;
      let closestDistance = Number.POSITIVE_INFINITY;

      pageElements.forEach((element) => {
        const rect = element.getBoundingClientRect();
        const pageCenter = rect.top + rect.height / 2;
        const distance = Math.abs(pageCenter - viewportCenter);
        const pageNumber = Number(element.dataset.pageNumber);

        if (Number.isFinite(pageNumber) && distance < closestDistance) {
          closestDistance = distance;
          closestPage = pageNumber;
        }
      });

      setCurrentPage((prev) => (prev === closestPage ? prev : closestPage));
    };

    updateCurrentPage();
    container.addEventListener("scroll", updateCurrentPage, {passive: true});

    return () => {
      container.removeEventListener("scroll", updateCurrentPage);
    };
  }, [numPages, pdfUrl]);

  useEffect(() => {
    setPageInput(String(currentPage));
  }, [currentPage]);

  const content = (
    <>
      {showHeader ? (
        <Box sx={{p: 2, borderBottom: "1px solid", borderColor: "divider"}}>
          <Stack spacing={0.5}>
            <Typography variant="h6" sx={{fontWeight: 800}}>
              PDF: {guideline?.title ?? guidelineLabel}
            </Typography>
            <Typography variant="body2" color="text.secondary">
              {references.length} reference{references.length === 1 ? "" : "s"} · {overlayBoxes.length} bounding box
              {overlayBoxes.length === 1 ? "" : "es"}
            </Typography>
            <Stack direction="row" spacing={1} alignItems="center">
              <InfoOutlinedIcon sx={{fontSize: 15}} color="action" />
              <Typography variant="body2" color="text.secondary">
                This panel shows the references highlighted in the PDF. To select one, click the corresponding entry in the reference list or click on the colored box.
              </Typography>
            </Stack>
          </Stack>
        </Box>
      ) : null}

      <Box sx={{px: showHeader ? 2 : 2, pt: showHeader ? 1.5 : 1, pb: 2, width: "100%"}}>
        <Stack
          direction="row"
          alignItems="center"
          justifyContent="space-between"
          sx={{width: "100%", gap: 1, flexWrap: "wrap"}}
        >
          <Stack direction="row" spacing={1} alignItems="center" sx={{flexWrap: "wrap"}}>
            <Typography variant="body2" sx={{fontWeight: 700}}>
              Page {Math.min(currentPage, Math.max(1, numPages))}/{Math.max(1, numPages)}
            </Typography>

            <Typography variant="body2" color="text.secondary">
              Go to page
            </Typography>

            <TextField
              size="small"
              type="number"
              value={pageInput}
              onChange={(event) => setPageInput(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter") {
                  event.preventDefault();
                  handlePageJump();
                }
              }}
              inputProps={{
                min: 1,
                max: Math.max(1, numPages),
                step: 1,
              }}
              sx={{width: 72}}
            />
          </Stack>

          {showReferenceToggle ? (
            <Stack direction="row" spacing={1} alignItems="center" sx={{ml: "auto"}}>
              <Typography variant="body2" color="text.secondary">
                Show references
              </Typography>
              <Switch
                size="small"
                checked={showReferences}
                onChange={(event) => setShowReferences(event.target.checked)}
              />
            </Stack>
          ) : null}
        </Stack>
      </Box>

      <Box sx={{pt: 0.5, flex: 1, minHeight: 0, overflow: "hidden"}}>
        {loading ? (
          <Box sx={{height: "100%", display: "flex", alignItems: "center", justifyContent: "center"}}>
            <CircularProgress />
          </Box>
        ) : error ? (
          <Alert severity="error">{error}</Alert>
        ) : !pdfUrl ? (
          <Alert severity="warning">No PDF available.</Alert>
        ) : (
          <Box
            ref={scrollAreaRef}
            sx={{
              height: "100%",
              maxHeight: `calc(${pageWidth}px * ${PDF_PAGE_RATIO} + 24px)`,
              minHeight: 0,
              overflow: "auto",
              bgcolor: "transparent",
              pt: 1,
              pb: 1,
              pl: 0,
              pr: 1,
            }}
          >
            <Document
              key={pdfUrl}
              file={pdfUrl}
              loading={
                <Box sx={{display: "flex", justifyContent: "center", py: 4}}>
                  <CircularProgress />
                </Box>
              }
              error={<Alert severity="error">Could not parse PDF.</Alert>}
              onLoadSuccess={(pdf) => {
                setNumPages(pdf.numPages);
              }}
            >
              {Array.from({length: numPages}, (_, index) => {
                const pageNumber = index + 1;
                return (
                  <Box key={pageNumber} data-page-number={pageNumber}>
                    <PdfPageWithOverlay
                      pageNumber={pageNumber}
                      pageWidth={pageWidth}
                      boxes={boxesByPage.get(pageNumber) ?? []}
                      showReferences={showReferences}
                      selectedReferenceId={selectedReferenceId}
                      onSelect={onSelect}
                    />
                  </Box>
                );
              })}
            </Document>
          </Box>
        )}
      </Box>

      {guideline?.download_information?.url ? (
        <Box sx={{pt: 1, px: showHeader ? 2 : 2}}>
          <Typography
            component="a"
            href={guideline.download_information.url}
            target="_blank"
            rel="noreferrer"
            variant="body2"
            sx={{
              color: "primary.main",
              textDecoration: "underline",
              wordBreak: "break-all",
            }}
          >
            {guideline.download_information.url}
          </Typography>
        </Box>
      ) : null}
    </>
  );

  if (!framed) {
    return (
      <Box
        sx={{
          height: "100%",
          minHeight: 0,
          display: "flex",
          flexDirection: "column",
          p: 0,
          overflow: "hidden",
        }}
      >
        {content}
      </Box>
    );
  }

  return (
    <Card variant="outlined" sx={{height: "100%", minHeight: 0}}>
      <CardContent
        sx={{
          height: "100%",
          minHeight: 0,
          display: "flex",
          flexDirection: "column",
          p: 0,
          overflow: "hidden",
        }}
      >
        {content}
      </CardContent>
    </Card>
  );
}
