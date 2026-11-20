# Plan: a computer-vision curriculum for Learn mode

Status: implemented (see the PR). Scope: classic and modern computer vision, taught on
spectral cubes (lab / close-range imaging, no Earth observation).

## Goal

Take a learner from "what is a pixel?" to the way a senior computer-vision engineer thinks,
in short hands-on lessons. Each idea is explained plainly, shown on the real viewer, and
checked with a click or a question. Hard ideas are simplified, never skipped.

## Sources

Lessons paraphrase and cite; they never copy text. Each lesson lists its reading at the end.

| Short name | Book |
| --- | --- |
| Gonzalez & Woods | *Digital Image Processing*, 4th ed. (2018); the 1992 edition covers the same basics |
| Szeliski | *Computer Vision: Algorithms and Applications*, 2nd ed. (2022) |
| Torralba, Isola & Freeman | *Foundations of Computer Vision* (2024) |
| Prince | *Computer Vision: Models, Learning, and Inference* (2012) |
| Hartley & Zisserman | *Multiple View Geometry in Computer Vision*, 2nd ed. (2004) |
| Ma, Soatto, Košecká & Sastry | *An Invitation to 3-D Vision* (2004) |
| Bishop | *Pattern Recognition and Machine Learning* (2006) |
| Goodfellow, Bengio & Courville | *Deep Learning* (2016) |

Spectral-specific lessons also cite the classic papers (Harris & Stephens 1988, Otsu 1979,
Reed & Yu 1990, Keshava & Mustard 2002, Savitzky & Golay 1964, Lowe 2004, Ronneberger et al.
2015, Dosovitskiy et al. 2021).

## Structure

Three levels, each split into units. The panel shows the level, then the unit, then the
lessons in order, with a done count per level. `*` marks a lesson that already existed.

### Basics: seeing images as data

| Unit | Lesson | Key ideas | Viewer demo |
| --- | --- | --- | --- |
| Images and pixels | What is a digital image? | sampling, quantisation, bit depth, pixel grid and coordinates | `quantize`, `subsample` |
| | What is a spectral cube? * | cube, band, pixel spectrum | band, 3D |
| | Bands and wavelengths * | chlorophyll, red edge | find a band |
| | Colour and composites * (+ metamers) | cones as three broad bands, metamerism, false colour | RGB |
| Pixel operations | Contrast and intensity transforms | negative, log, gamma, display stretch | band math |
| | Histograms | histogram, percentiles, equalisation | `equalize`, Stretch panel |
| | Band math and indices * | ratios, normalised difference, masks | band math |
| | Thresholds and Otsu's method | binary masks, choosing a threshold automatically | `otsu` |
| | Comparing materials * | brightness vs shape, spectral angle | similarity |

### Intermediate: neighbourhoods, frequencies, shapes and clean data

| Unit | Lesson | Key ideas | Viewer demo |
| --- | --- | --- | --- |
| Filters | Neighbourhoods and convolution | kernels, box and Gaussian blur, borders, linear shift-invariant systems, separability | `box`, `gauss` |
| | Noise and denoising | Gaussian vs impulse noise, mean vs median, the edge cost | `median` |
| | Gradients and edges | derivatives, Sobel, gradient magnitude, Laplacian, smoothing first, Canny's idea | `dx`, `dy`, `grad`, `laplace` |
| | Sharpening | unsharp masking, high boost, noise amplification | band math |
| | The frequency domain | Fourier magnitude, low / high pass, stripes as spikes, convolution theorem | `fft`, `lowpass`, `highpass` |
| | Sampling, aliasing and pyramids | Nyquist, blur before you shrink, image pyramids | `subsample`, `gauss` |
| Shapes and regions | Morphology | erosion, dilation, opening, closing | `erode`, `dilate`, `opening`, `closing` |
| | Regions and shape | connected components, area, size filters, shape descriptors | `components`, `area` |
| From raw data to clean data | Spotting sensor problems * · From raw counts to reflectance * · Aligning the bands * · Repairing defects * · Smoothing and normalising spectra * | | pipelines |

### Advanced: features, geometry, statistics and learning

| Unit | Lesson | Key ideas | Viewer demo |
| --- | --- | --- | --- |
| Features and geometry | Corners and local features | structure tensor, Harris, scale space, descriptors, matching, RANSAC | `harris` |
| | Cameras and image formation | pinhole, intrinsics / extrinsics, distortion, how spectral cameras scan | concept + capture demo |
| | Geometry of several views | homography, DLT, epipolar geometry, essential / fundamental matrix, triangulation, bundle adjustment | concept |
| Statistics without labels | Principal component analysis * | | PCA |
| | Clustering into segments | k-means, choosing k, segmentation vs classification | `kmeans` |
| | Mixed pixels and unmixing | linear mixing model, endmembers, abundances | pins, spectra |
| | Finding the unusual * | | anomaly |
| Learning from data | Supervised classification | features, nearest centroid, linear classifiers, overfitting, bias and variance | similarity |
| | Evaluating a model honestly | confusion matrix, precision / recall, IoU, splits, spatial leakage, imbalance | concept |
| | Convolutional networks | a layer = filter + nonlinearity + pooling, receptive field, learning by gradient descent, spectral-spatial convolutions | band math |
| | Modern architectures | residual nets, U-Net, attention and transformers, self-supervised pretraining, transfer to new sensors | concept |
| | Thinking like a senior engineer | debugging order, baselines, failure analysis, budgets, drift | scenarios |

## Engine changes (small, no new framework)

- `level` becomes `basics | intermediate | advanced`; new optional `unit` (subheading) and
  `reading` (list of references shown when a lesson ends).
- Band math gains image functions from a new pure-NumPy module `compute/spatial.py` (2-D arrays
  in and out, NaN-aware), so lessons stay plain TOML and a faster backend can replace the
  module. `kmeans(k)` works on the whole cube. The viewer's band-math box gets them for free.
- A test evaluates every bundled lesson's band-math expression on its demo cube, so a typo in
  a lesson fails CI.

## How accuracy was checked

- Every claim about the demo scene (which object a map selects, which band is darkest, how
  many regions a mask has, precision / recall numbers) was computed from the cube's label map,
  and every step was rendered and looked at, since the display stretch can make a correct
  map look misleading.
- Fixes this turned up: the demo leaf had no chlorophyll dip at 670 nm (now it does), Harris
  and k-means steps were rewritten to match what the data really shows, the Fourier transform
  is windowed so image borders don't draw a false cross, and aliasing is taught on a zone
  plate because the demo's stripes are not a clean single frequency.
- References are cited by chapter and topic only (no section numbers), and lessons
  paraphrase.

## Learning design

- One idea per step, shown on the viewer before it is named, then checked with a click or a
  question whose feedback explains *why*.
- Each level reuses the previous one: convolution returns in edges, pyramids, CNNs; Otsu and
  morphology return in regions and evaluation; calibration returns in cameras and the
  capstone.
- Wrong answers get a hint toward the reasoning, not the answer.

## Left out

Topics the viewer can't show and a short lesson can't do justice to: wavelets and compression,
active contours, optical flow and tracking, stereo matching, generative models. They are good
next lessons once the viewer can show them.
