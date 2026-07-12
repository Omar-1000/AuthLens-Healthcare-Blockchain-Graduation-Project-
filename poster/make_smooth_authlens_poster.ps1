$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing

$W = 1600
$H = 2400
$OutPath = 'C:\Users\abodk\Desktop\eheath-system\poster\authlens-healthcare-blockchain-smooth.png'
$UjLogoPath = 'C:\Users\abodk\Desktop\University_of_Jordan_Logo.png'

function C([int]$a, [int]$r, [int]$g, [int]$b) {
  return [System.Drawing.Color]::FromArgb($a, $r, $g, $b)
}

function RF([float]$x, [float]$y, [float]$w, [float]$h) {
  return [System.Drawing.RectangleF]::new($x, $y, $w, $h)
}

function New-RoundPath([float]$x, [float]$y, [float]$w, [float]$h, [float]$r) {
  $p = [System.Drawing.Drawing2D.GraphicsPath]::new()
  $d = $r * 2
  $p.AddArc($x, $y, $d, $d, 180, 90)
  $p.AddArc($x + $w - $d, $y, $d, $d, 270, 90)
  $p.AddArc($x + $w - $d, $y + $h - $d, $d, $d, 0, 90)
  $p.AddArc($x, $y + $h - $d, $d, $d, 90, 90)
  $p.CloseFigure()
  return $p
}

function New-RibbonPath([float]$x, [float]$y, [float]$w, [float]$h, [float]$cut) {
  $p = [System.Drawing.Drawing2D.GraphicsPath]::new()
  $pts = @(
    [System.Drawing.PointF]::new($x + $cut, $y),
    [System.Drawing.PointF]::new($x + $w - $cut, $y),
    [System.Drawing.PointF]::new($x + $w, $y + $h / 2),
    [System.Drawing.PointF]::new($x + $w - $cut, $y + $h),
    [System.Drawing.PointF]::new($x + $cut, $y + $h),
    [System.Drawing.PointF]::new($x, $y + $h / 2)
  )
  $p.AddPolygon($pts)
  return $p
}

function Draw-SoftGlow($g, [float]$x, [float]$y, [float]$w, [float]$h, [float]$r) {
  for ($i = 7; $i -ge 1; $i--) {
    $pad = $i * 4
    $alpha = 12 + (7 - $i) * 8
    $pen = [System.Drawing.Pen]::new((C $alpha 0 210 255), [float]($i * 2.2))
    $path = New-RoundPath ($x - $pad) ($y - $pad) ($w + 2 * $pad) ($h + 2 * $pad) ($r + $pad)
    $g.DrawPath($pen, $path)
    $path.Dispose()
    $pen.Dispose()
  }
}

function Draw-Panel($g, [float]$x, [float]$y, [float]$w, [float]$h, [string]$title, [string]$num, [bool]$dark = $false) {
  Draw-SoftGlow $g $x $y $w $h 22
  $path = New-RoundPath $x $y $w $h 22
  if ($dark) {
    $fill = [System.Drawing.Drawing2D.LinearGradientBrush]::new((RF $x $y $w $h), (C 255 2 14 64), (C 255 4 46 122), 25)
  } else {
    $fill = [System.Drawing.Drawing2D.LinearGradientBrush]::new((RF $x $y $w $h), (C 250 250 255 255), (C 238 207 235 252), 90)
  }
  $g.FillPath($fill, $path)
  $pen = [System.Drawing.Pen]::new((C 245 0 128 255), 2.5)
  $g.DrawPath($pen, $path)
  $innerPen = [System.Drawing.Pen]::new((C 125 255 255 255), 1.2)
  $g.DrawPath($innerPen, $path)
  $fill.Dispose(); $pen.Dispose(); $innerPen.Dispose(); $path.Dispose()

  if ($title.Length -gt 0) {
    $tw = [Math]::Max(320, 18 * $title.Length + 115)
    if ($tw -gt $w - 44) { $tw = $w - 44 }
    $tx = $x + ($w - $tw) / 2
    Draw-Ribbon $g $tx ($y - 15) $tw 50 $title 25 $num
  }
}

function Draw-Ribbon($g, [float]$x, [float]$y, [float]$w, [float]$h, [string]$text, [float]$fontSize, [string]$num = '') {
  $path = New-RibbonPath $x $y $w $h 46
  $fill = [System.Drawing.Drawing2D.LinearGradientBrush]::new((RF $x $y $w $h), (C 255 0 124 255), (C 255 0 16 90), 90)
  $g.FillPath($fill, $path)
  $pen = [System.Drawing.Pen]::new((C 240 45 233 255), 2)
  $g.DrawPath($pen, $path)

  if ($num -ne '') {
    $badge = New-RoundPath ($x + 22) ($y + 7) 38 36 8
    $white = [System.Drawing.SolidBrush]::new([System.Drawing.Color]::White)
    $g.FillPath($white, $badge)
    $nb = [System.Drawing.SolidBrush]::new((C 255 0 45 133))
    $nf = [System.Drawing.Font]::new('Segoe UI', 24, [System.Drawing.FontStyle]::Bold, [System.Drawing.GraphicsUnit]::Pixel)
    $sf = [System.Drawing.StringFormat]::new()
    $sf.Alignment = [System.Drawing.StringAlignment]::Center
    $sf.LineAlignment = [System.Drawing.StringAlignment]::Center
    $g.DrawString($num, $nf, $nb, (RF ($x + 22) ($y + 7) 38 36), $sf)
    $white.Dispose(); $nb.Dispose(); $nf.Dispose(); $sf.Dispose(); $badge.Dispose()
    $textX = $x + 68
    $textW = $w - 84
  } else {
    $textX = $x + 20
    $textW = $w - 40
  }

  $font = [System.Drawing.Font]::new('Segoe UI', $fontSize, [System.Drawing.FontStyle]::Bold, [System.Drawing.GraphicsUnit]::Pixel)
  $whiteText = [System.Drawing.SolidBrush]::new([System.Drawing.Color]::White)
  $shadow = [System.Drawing.SolidBrush]::new((C 185 0 12 70))
  $fmt = [System.Drawing.StringFormat]::new()
  $fmt.Alignment = [System.Drawing.StringAlignment]::Center
  $fmt.LineAlignment = [System.Drawing.StringAlignment]::Center
  $g.DrawString($text, $font, $shadow, (RF ($textX + 2) ($y + 2) $textW $h), $fmt)
  $g.DrawString($text, $font, $whiteText, (RF $textX $y $textW $h), $fmt)
  $font.Dispose(); $whiteText.Dispose(); $shadow.Dispose(); $fmt.Dispose(); $fill.Dispose(); $pen.Dispose(); $path.Dispose()
}

function Draw-Text($g, [string]$text, [float]$x, [float]$y, [float]$w, [float]$h, [float]$size, [int]$style, $color, [string]$align = 'Near') {
  $font = [System.Drawing.Font]::new('Segoe UI', $size, $style, [System.Drawing.GraphicsUnit]::Pixel)
  $brush = [System.Drawing.SolidBrush]::new($color)
  $sf = [System.Drawing.StringFormat]::new()
  if ($align -eq 'Center') { $sf.Alignment = [System.Drawing.StringAlignment]::Center } else { $sf.Alignment = [System.Drawing.StringAlignment]::Near }
  $sf.LineAlignment = [System.Drawing.StringAlignment]::Near
  $g.DrawString($text, $font, $brush, (RF $x $y $w $h), $sf)
  $font.Dispose(); $brush.Dispose(); $sf.Dispose()
}

function Draw-CenteredText($g, [string]$text, [float]$x, [float]$y, [float]$w, [float]$h, [float]$size, [int]$style, $color) {
  $font = [System.Drawing.Font]::new('Segoe UI', $size, $style, [System.Drawing.GraphicsUnit]::Pixel)
  $brush = [System.Drawing.SolidBrush]::new($color)
  $sf = [System.Drawing.StringFormat]::new()
  $sf.Alignment = [System.Drawing.StringAlignment]::Center
  $sf.LineAlignment = [System.Drawing.StringAlignment]::Center
  $g.DrawString($text, $font, $brush, (RF $x $y $w $h), $sf)
  $font.Dispose(); $brush.Dispose(); $sf.Dispose()
}

function Draw-TitleText($g, [string]$text, [float]$x, [float]$y, [float]$w, [float]$h, [float]$size) {
  $font = [System.Drawing.Font]::new('Segoe UI', $size, [System.Drawing.FontStyle]::Bold, [System.Drawing.GraphicsUnit]::Pixel)
  $sf = [System.Drawing.StringFormat]::new()
  $sf.Alignment = [System.Drawing.StringAlignment]::Center
  $sf.LineAlignment = [System.Drawing.StringAlignment]::Center
  $shadow = [System.Drawing.SolidBrush]::new((C 220 0 6 45))
  $white = [System.Drawing.SolidBrush]::new((C 235 255 255 255))
  $blue = [System.Drawing.Drawing2D.LinearGradientBrush]::new((RF $x $y $w $h), (C 255 3 19 99), (C 255 0 202 255), 0)
  $g.DrawString($text, $font, $shadow, (RF ($x + 7) ($y + 9) $w $h), $sf)
  $g.DrawString($text, $font, $white, (RF ($x + 2) ($y + 2) $w $h), $sf)
  $g.DrawString($text, $font, $blue, (RF $x $y $w $h), $sf)
  $font.Dispose(); $sf.Dispose(); $shadow.Dispose(); $white.Dispose(); $blue.Dispose()
}

function Draw-Avatar($g, [float]$cx, [float]$cy, [float]$r) {
  $bg = [System.Drawing.Drawing2D.LinearGradientBrush]::new((RF ($cx-$r) ($cy-$r) ($r*2) ($r*2)), (C 255 16 38 105), (C 255 0 7 38), 90)
  $g.FillEllipse($bg, $cx-$r, $cy-$r, $r*2, $r*2)
  $pen = [System.Drawing.Pen]::new([System.Drawing.Color]::White, 3)
  $g.DrawEllipse($pen, $cx-$r, $cy-$r, $r*2, $r*2)
  $white = [System.Drawing.SolidBrush]::new([System.Drawing.Color]::White)
  $g.FillEllipse($white, $cx-15, $cy-23, 30, 30)
  $g.FillEllipse($white, $cx-32, $cy+5, 64, 46)
  $bg.Dispose(); $pen.Dispose(); $white.Dispose()
}

function Draw-CircleIcon($g, [string]$kind, [float]$cx, [float]$cy, [float]$s) {
  $r = $s / 2
  $fill = [System.Drawing.Drawing2D.LinearGradientBrush]::new((RF ($cx-$r) ($cy-$r) $s $s), (C 255 18 213 255), (C 255 0 31 130), 145)
  $g.FillEllipse($fill, $cx-$r, $cy-$r, $s, $s)
  $pen1 = [System.Drawing.Pen]::new((C 230 255 255 255), 3)
  $g.DrawEllipse($pen1, $cx-$r, $cy-$r, $s, $s)
  $whitePen = [System.Drawing.Pen]::new([System.Drawing.Color]::White, [Math]::Max(3, $s/17))
  $whitePen.StartCap = [System.Drawing.Drawing2D.LineCap]::Round
  $whitePen.EndCap = [System.Drawing.Drawing2D.LineCap]::Round
  $whitePen.LineJoin = [System.Drawing.Drawing2D.LineJoin]::Round
  $white = [System.Drawing.SolidBrush]::new([System.Drawing.Color]::White)
  $blue = [System.Drawing.SolidBrush]::new((C 255 0 32 115))

  switch ($kind) {
    'person' {
      $g.FillEllipse($white, $cx-$s*.13, $cy-$s*.25, $s*.26, $s*.26)
      $g.FillEllipse($white, $cx-$s*.25, $cy, $s*.5, $s*.34)
    }
    'lock' {
      $g.DrawArc($whitePen, $cx-$s*.18, $cy-$s*.28, $s*.36, $s*.35, 180, 180)
      $g.FillRectangle($white, $cx-$s*.25, $cy-$s*.04, $s*.5, $s*.34)
    }
    'shield' {
      $pts = @(
        [System.Drawing.PointF]::new($cx, $cy-$s*.34),
        [System.Drawing.PointF]::new($cx+$s*.28, $cy-$s*.22),
        [System.Drawing.PointF]::new($cx+$s*.22, $cy+$s*.21),
        [System.Drawing.PointF]::new($cx, $cy+$s*.36),
        [System.Drawing.PointF]::new($cx-$s*.22, $cy+$s*.21),
        [System.Drawing.PointF]::new($cx-$s*.28, $cy-$s*.22)
      )
      $g.DrawPolygon($whitePen, $pts)
      $g.DrawLines($whitePen, @([System.Drawing.PointF]::new($cx-$s*.15,$cy+$s*.02),[System.Drawing.PointF]::new($cx-$s*.03,$cy+$s*.16),[System.Drawing.PointF]::new($cx+$s*.18,$cy-$s*.12)))
    }
    'doc' {
      $g.FillRectangle($white, $cx-$s*.24, $cy-$s*.31, $s*.42, $s*.56)
      $g.DrawLine($whitePen, $cx-$s*.13, $cy-$s*.09, $cx+$s*.11, $cy-$s*.09)
      $g.DrawLine($whitePen, $cx-$s*.13, $cy+$s*.04, $cx+$s*.13, $cy+$s*.04)
    }
    'eye' {
      $g.DrawArc($whitePen, $cx-$s*.32, $cy-$s*.18, $s*.64, $s*.36, 200, 140)
      $g.DrawArc($whitePen, $cx-$s*.32, $cy-$s*.18, $s*.64, $s*.36, 20, 140)
      $g.FillEllipse($white, $cx-$s*.09, $cy-$s*.09, $s*.18, $s*.18)
    }
    'cubes' {
      foreach ($p in @(@(-.18,-.21),@(.12,-.02),@(-.18,.17))) {
        $g.DrawRectangle($whitePen, $cx+$s*$p[0], $cy+$s*$p[1], $s*.18, $s*.18)
      }
    }
    'phone' {
      $g.DrawRectangle($whitePen, $cx-$s*.18, $cy-$s*.31, $s*.36, $s*.62)
      $g.FillEllipse($white, $cx-$s*.05, $cy+$s*.22, $s*.1, $s*.1)
    }
    'click' {
      $g.DrawLines($whitePen, @([System.Drawing.PointF]::new($cx-$s*.17,$cy-$s*.1),[System.Drawing.PointF]::new($cx,$cy+$s*.26),[System.Drawing.PointF]::new($cx+$s*.22,$cy-$s*.05)))
      $g.DrawLine($whitePen, $cx+$s*.2, $cy-$s*.24, $cx+$s*.34, $cy-$s*.36)
      $g.DrawLine($whitePen, $cx-$s*.18, $cy-$s*.28, $cx-$s*.31, $cy-$s*.42)
    }
    'database' {
      $g.DrawEllipse($whitePen, $cx-$s*.26, $cy-$s*.28, $s*.52, $s*.18)
      $g.DrawRectangle($whitePen, $cx-$s*.26, $cy-$s*.19, $s*.52, $s*.45)
      $g.DrawArc($whitePen, $cx-$s*.26, $cy+$s*.17, $s*.52, $s*.18, 0, 180)
    }
    'robot' {
      $g.FillRectangle($white, $cx-$s*.24, $cy-$s*.16, $s*.48, $s*.33)
      $g.FillEllipse($blue, $cx-$s*.14, $cy-$s*.06, $s*.08, $s*.08)
      $g.FillEllipse($blue, $cx+$s*.06, $cy-$s*.06, $s*.08, $s*.08)
      $g.DrawLine($whitePen, $cx, $cy-$s*.16, $cx, $cy-$s*.33)
    }
    'keyboard' {
      $g.DrawRectangle($whitePen, $cx-$s*.31, $cy-$s*.19, $s*.62, $s*.38)
      for ($kx = -2; $kx -le 2; $kx++) {
        for ($ky = -1; $ky -le 1; $ky++) {
          $g.FillEllipse($white, $cx+$kx*$s*.11-$s*.025, $cy+$ky*$s*.1-$s*.025, $s*.05, $s*.05)
        }
      }
    }
    'wallet' {
      $g.DrawRectangle($whitePen, $cx-$s*.31, $cy-$s*.18, $s*.58, $s*.36)
      $g.DrawRectangle($whitePen, $cx+$s*.02, $cy-$s*.08, $s*.28, $s*.18)
      $g.FillEllipse($white, $cx+$s*.17, $cy-$s*.01, $s*.05, $s*.05)
    }
    default {
      $f = [System.Drawing.Font]::new('Segoe UI', $s*.42, [System.Drawing.FontStyle]::Bold, [System.Drawing.GraphicsUnit]::Pixel)
      $sf = [System.Drawing.StringFormat]::new()
      $sf.Alignment = [System.Drawing.StringAlignment]::Center
      $sf.LineAlignment = [System.Drawing.StringAlignment]::Center
      $g.DrawString($kind, $f, $white, (RF ($cx-$r) ($cy-$r) $s $s), $sf)
      $f.Dispose(); $sf.Dispose()
    }
  }
  $fill.Dispose(); $pen1.Dispose(); $whitePen.Dispose(); $white.Dispose(); $blue.Dispose()
}

function Draw-Bullet($g, [string]$kind, [string]$text, [float]$x, [float]$y, [float]$w, [float]$size = 72) {
  Draw-CircleIcon $g $kind ($x + $size/2) ($y + $size/2) $size
  Draw-Text $g $text ($x + $size + 22) ($y + 8) ($w - $size - 24) ($size + 18) 23 ([System.Drawing.FontStyle]::Bold) (C 255 0 24 121)
}

function Draw-Pillar($g, [float]$x, [float]$y, [float]$w, [float]$h, [string]$icon, [string]$title, [string]$body) {
  $p = New-RoundPath $x $y $w $h 17
  $fill = [System.Drawing.Drawing2D.LinearGradientBrush]::new((RF $x $y $w $h), (C 245 248 253 255), (C 230 219 239 253), 90)
  $g.FillPath($fill, $p)
  $pen = [System.Drawing.Pen]::new((C 170 0 130 255), 1.5)
  $g.DrawPath($pen, $p)
  Draw-CircleIcon $g $icon ($x + 62) ($y + $h/2) 74
  Draw-Text $g $title ($x + 110) ($y + 14) ($w - 120) 54 19 ([System.Drawing.FontStyle]::Bold) (C 255 0 24 128) 'Center'
  Draw-Text $g $body ($x + 110) ($y + 68) ($w - 120) 56 12.5 ([System.Drawing.FontStyle]::Bold) (C 255 0 24 122) 'Center'
  $fill.Dispose(); $pen.Dispose(); $p.Dispose()
}

function Draw-Feature($g, [float]$x, [float]$y, [float]$w, [float]$h, [string]$icon, [string]$text) {
  Draw-CircleIcon $g $icon ($x + $w/2) ($y + 36) 54
  Draw-Text $g $text ($x + 8) ($y + 66) ($w - 16) ($h - 66) 14 ([System.Drawing.FontStyle]::Bold) (C 255 0 24 122) 'Center'
}

function Draw-TechItem($g, [float]$x, [float]$w, [string]$icon, [string]$text) {
  Draw-CircleIcon $g $icon ($x + 46) 2318 58
  Draw-Text $g $text ($x + 88) 2288 ($w - 92) 66 18 ([System.Drawing.FontStyle]::Bold) (C 255 0 24 122)
}

$bmp = [System.Drawing.Bitmap]::new($W, $H, [System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.CompositingQuality = [System.Drawing.Drawing2D.CompositingQuality]::HighQuality
$g.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
$g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
$g.TextRenderingHint = [System.Drawing.Text.TextRenderingHint]::AntiAliasGridFit
$g.PixelOffsetMode = [System.Drawing.Drawing2D.PixelOffsetMode]::HighQuality

# Background.
$bg = [System.Drawing.Drawing2D.LinearGradientBrush]::new((RF 0 0 $W $H), (C 255 0 7 42), (C 255 7 107 207), 90)
$g.FillRectangle($bg, 0, 0, $W, $H)
$bg.Dispose()
$centerGlow = [System.Drawing.Drawing2D.PathGradientBrush]::new(@(
  [System.Drawing.PointF]::new(180, 120),
  [System.Drawing.PointF]::new(1420, 120),
  [System.Drawing.PointF]::new(1500, 740),
  [System.Drawing.PointF]::new(100, 740)
))
$centerGlow.CenterColor = C 235 246 254 255
$centerGlow.SurroundColors = @((C 0 246 254 255))
$g.FillRectangle($centerGlow, 0, 80, $W, 760)
$centerGlow.Dispose()

$gridPen = [System.Drawing.Pen]::new((C 45 55 225 255), 1)
for ($x = 0; $x -le $W; $x += 72) { $g.DrawLine($gridPen, $x, 0, $x, $H) }
for ($y = 0; $y -le $H; $y += 72) { $g.DrawLine($gridPen, 0, $y, $W, $y) }
$gridPen.Dispose()
$rnd = [Random]::new(8)
$circuitPen = [System.Drawing.Pen]::new((C 100 0 225 255), 2)
for ($i = 0; $i -lt 120; $i++) {
  $x = $rnd.Next(0, $W)
  $y = $rnd.Next(0, $H)
  $len = $rnd.Next(22, 90)
  $g.DrawLine($circuitPen, $x, $y, $x + $len, $y)
  if ($i % 3 -eq 0) { $g.FillEllipse([System.Drawing.SolidBrush]::new((C 150 0 225 255)), $x + $len - 3, $y - 3, 6, 6) }
}
$circuitPen.Dispose()

# Outer border.
$borderPen = [System.Drawing.Pen]::new((C 230 54 224 255), 4)
$g.DrawRectangle($borderPen, 4, 4, $W - 8, $H - 8)
$borderPen.Dispose()

# Top student bar.
Draw-SoftGlow $g 120 25 1360 106 22
$topPath = New-RoundPath 120 25 1360 106 22
$topFill = [System.Drawing.Drawing2D.LinearGradientBrush]::new((RF 120 25 1360 106), (C 255 4 20 78), (C 255 1 7 35), 90)
$g.FillPath($topFill, $topPath)
$topPen = [System.Drawing.Pen]::new((C 245 60 225 255), 2.5)
$g.DrawPath($topPen, $topPath)
$topFill.Dispose(); $topPen.Dispose(); $topPath.Dispose()
$sepPen = [System.Drawing.Pen]::new((C 180 32 225 255), 2)
$g.DrawLine($sepPen, 555, 45, 555, 110)
$g.DrawLine($sepPen, 1045, 45, 1045, 110)
$sepPen.Dispose()
$students = @(
  @{Name='Omar Ayesh'; Id='0226526'; X=165},
  @{Name='Abdelrahman Khalil'; Id='0227165'; X=650},
  @{Name='Abdelrahman Abujee''p'; Id='0227653'; X=1135}
)
foreach ($s in $students) {
  Draw-Avatar $g ($s.X + 48) 78 40
  Draw-Text $g $s.Name ($s.X + 100) 48 310 34 27 ([System.Drawing.FontStyle]::Bold) (C 255 255 255 255)
  Draw-Text $g $s.Id ($s.X + 100) 82 250 36 29 ([System.Drawing.FontStyle]::Bold) (C 255 0 245 255)
}

Draw-Ribbon $g 500 125 600 50 'Supervisor: Dr. Oraib Abualghanam' 26 ''

# Hero logos.
Draw-CircleIcon $g 'database' 270 330 230
Draw-Text $g '10100100011' 218 310 105 28 19 ([System.Drawing.FontStyle]::Bold) (C 255 255 255 255) 'Center'
Draw-CenteredText $g 'AuthLens' 585 482 430 70 55 ([System.Drawing.FontStyle]::Bold) (C 255 0 35 120)

# Center logo shield.
$shieldPen = [System.Drawing.Pen]::new((C 255 0 74 180), 9)
$whitePen = [System.Drawing.Pen]::new([System.Drawing.Color]::White, 6)
$shield = [System.Drawing.Drawing2D.GraphicsPath]::new()
$shield.AddPolygon(@(
  [System.Drawing.PointF]::new(800, 160),
  [System.Drawing.PointF]::new(915, 210),
  [System.Drawing.PointF]::new(895, 390),
  [System.Drawing.PointF]::new(800, 460),
  [System.Drawing.PointF]::new(705, 390),
  [System.Drawing.PointF]::new(685, 210)
))
$sfGrad = [System.Drawing.Drawing2D.LinearGradientBrush]::new((RF 680 150 240 320), (C 245 255 255 255), (C 235 172 224 255), 90)
$g.FillPath($sfGrad, $shield)
$g.DrawPath($shieldPen, $shield)
$g.DrawPath($whitePen, $shield)
Draw-CircleIcon $g 'shield' 800 285 120
Draw-CircleIcon $g 'lock' 800 405 78
$shield.Dispose(); $shieldPen.Dispose(); $whitePen.Dispose(); $sfGrad.Dispose()

if (Test-Path $UjLogoPath) {
  $uj = [System.Drawing.Image]::FromFile($UjLogoPath)
  $logoH = 350
  $logoW = [int]([double]$logoH * $uj.Width / $uj.Height)
  $glow = [System.Drawing.SolidBrush]::new((C 85 255 255 255))
  $g.FillEllipse($glow, 1200, 190, 310, 330)
  $glow.Dispose()
  $g.DrawImage($uj, 1228, 162, $logoW, $logoH)
  $uj.Dispose()
}

Draw-TitleText $g 'AuthLens Healthcare Blockchain' 55 555 1490 95 78
Draw-Ribbon $g 185 665 1230 58 'PROTECTING SENSITIVE HEALTHCARE DATA FROM CYBER ATTACKS' 31 ''

# Description.
$descPath = New-RoundPath 170 730 1260 150 18
$descFill = [System.Drawing.SolidBrush]::new((C 225 233 248 255))
$g.FillPath($descFill, $descPath)
$descPen = [System.Drawing.Pen]::new((C 150 0 150 255), 2)
$g.DrawPath($descPen, $descPath)
$desc = 'AuthLens is a secure e-health platform that gives patients control over access to their medical records. It combines zero-trust verification, patient approval workflows, encrypted off-chain storage, and blockchain integrity proof to build a trusted healthcare ecosystem.'
Draw-Text $g $desc 235 752 1130 112 24 ([System.Drawing.FontStyle]::Bold) (C 255 0 23 125) 'Center'
$descPath.Dispose(); $descFill.Dispose(); $descPen.Dispose()

# Top content panels.
Draw-Panel $g 28 915 420 455 'PROBLEM' '1'
Draw-Bullet $g 'person' 'Unauthorized access to patient records' 58 980 355 70
Draw-Bullet $g 'shield' 'Weak identity verification in e-health systems' 58 1073 355 70
Draw-Bullet $g 'doc' 'Risk of tampering with medical records' 58 1166 355 70
Draw-Bullet $g 'eye' 'Limited patient control and poor access transparency' 58 1259 355 70

Draw-Panel $g 468 915 420 455 'SOLUTION' '2'
Draw-Bullet $g 'person' 'Patient-controlled approval before doctor access' 498 980 355 70
Draw-Bullet $g 'shield' 'Zero-Trust verification at every access step' 498 1073 355 70
Draw-Bullet $g 'cubes' 'Blockchain integrity proof for records and approvals' 498 1166 355 70
Draw-Bullet $g 'lock' 'Encrypted off-chain storage for privacy protection' 498 1259 355 70

Draw-Panel $g 908 915 664 455 'SYSTEM ARCHITECTURE' '3'
$blueText = C 255 0 24 122
$boxFill = [System.Drawing.SolidBrush]::new((C 242 247 253 255))
$boxPen = [System.Drawing.Pen]::new((C 220 0 130 255), 2)
$arrowPen = [System.Drawing.Pen]::new((C 255 0 64 180), 4)
$arrowPen.EndCap = [System.Drawing.Drawing2D.LineCap]::ArrowAnchor
Draw-Panel $g 936 990 110 250 '' ''
Draw-CircleIcon $g 'person' 991 1045 46; Draw-Text $g 'Patient' 952 1072 78 28 16 ([System.Drawing.FontStyle]::Bold) $blueText 'Center'
Draw-CircleIcon $g 'person' 991 1130 46; Draw-Text $g 'Doctor' 952 1157 78 28 16 ([System.Drawing.FontStyle]::Bold) $blueText 'Center'
Draw-CircleIcon $g 'person' 991 1215 46; Draw-Text $g 'Admin' 952 1242 78 28 16 ([System.Drawing.FontStyle]::Bold) $blueText 'Center'
Draw-Panel $g 1094 1048 125 130 '' ''
Draw-CircleIcon $g 'F' 1156 1090 54
Draw-Text $g 'Flask Backend' 1112 1126 90 45 18 ([System.Drawing.FontStyle]::Bold) $blueText 'Center'
Draw-CircleIcon $g 'database' 1322 1106 96
Draw-Text $g 'MySQL Database' 1270 1160 104 45 18 ([System.Drawing.FontStyle]::Bold) $blueText 'Center'
$g.DrawLine($arrowPen, 1047, 1112, 1088, 1112)
$g.DrawLine($arrowPen, 1224, 1112, 1262, 1112)
Draw-Panel $g 1407 990 135 250 '' ''
Draw-CircleIcon $g 'doc' 1474 1038 46; Draw-Text $g 'Access Requests' 1440 1063 72 42 15 ([System.Drawing.FontStyle]::Bold) $blueText 'Center'
Draw-CircleIcon $g 'doc' 1474 1135 46; Draw-Text $g 'Audit Logs' 1440 1160 72 34 15 ([System.Drawing.FontStyle]::Bold) $blueText 'Center'
Draw-CircleIcon $g 'lock' 1474 1232 46; Draw-Text $g 'Encrypted Medical Records' 1436 1258 82 45 15 ([System.Drawing.FontStyle]::Bold) $blueText 'Center'
$g.DrawLine($arrowPen, 1376, 1112, 1405, 1112)
Draw-Panel $g 975 1265 230 75 '' ''
Draw-CircleIcon $g 'M' 1018 1302 54
Draw-Text $g 'MetaMask Wallet Authentication' 1060 1280 125 42 17 ([System.Drawing.FontStyle]::Bold) $blueText
Draw-Panel $g 1230 1265 285 75 '' ''
Draw-CircleIcon $g 'E' 1273 1302 54
Draw-Text $g 'Ganache / Ethereum Blockchain' 1318 1280 170 42 17 ([System.Drawing.FontStyle]::Bold) $blueText
$g.DrawLine($arrowPen, 1156, 1178, 1156, 1260)
$g.DrawLine($arrowPen, 1322, 1178, 1322, 1260)
$boxFill.Dispose(); $boxPen.Dispose(); $arrowPen.Dispose()

# Core trust pillars.
Draw-Panel $g 28 1400 1544 220 '' ''
Draw-Ribbon $g 560 1376 480 52 'CORE TRUST PILLARS' 29 ''
Draw-Pillar $g 48 1460 360 130 'shield' 'ZERO TRUST' 'Every access is verified. No access is approved by default.'
Draw-Pillar $g 426 1460 360 130 'lock' 'HIGH PRIVACY' 'Medical data stays protected and shared only with permission.'
Draw-Pillar $g 804 1460 360 130 'cubes' 'BLOCKCHAIN INTEGRITY' 'Hashes and approvals are stored as tamper-evident proof.'
Draw-Pillar $g 1182 1460 360 130 'doc' 'AUTHENTICATION WITH BLOCKCHAIN' 'Blockchain-backed authentication strengthens identity verification and secure access.'

# Workflow.
Draw-Panel $g 28 1650 1544 230 'SECURE ACCESS WORKFLOW' '4'
$stepXs = @(155, 440, 725, 1010, 1295)
$stepIcons = @('person','phone','click','shield','doc')
$stepTexts = @('Doctor requests access','Patient receives request','Patient approves or rejects','System verifies identity and permission','Encrypted record access + blockchain proof')
for ($i=0; $i -lt 5; $i++) {
  $cx = $stepXs[$i]
  Draw-CircleIcon $g $stepIcons[$i] $cx 1760 95
  Draw-CircleIcon $g ([string]($i+1)) ($cx-55) 1698 42
  Draw-Text $g $stepTexts[$i] ($cx-100) 1818 200 58 16.5 ([System.Drawing.FontStyle]::Bold) $blueText 'Center'
  if ($i -lt 4) {
    $ap = [System.Drawing.Pen]::new((C 255 0 114 218), 9)
    $ap.EndCap = [System.Drawing.Drawing2D.LineCap]::ArrowAnchor
    $g.DrawLine($ap, $cx + 90, 1760, $stepXs[$i+1] - 85, 1760)
    $ap.Dispose()
  }
}

# Features and conclusion.
Draw-Panel $g 28 1915 725 320 'FEATURES' '5'
$fw = 168; $fh = 115; $fx0 = 58; $fy0 = 1982
$features = @(
  @('lock','Encrypted off-chain records'),
  @('person','Role-based access control'),
  @('doc','Audit logs and traceability'),
  @('shield','OTP + CAPTCHA'),
  @('keyboard','Virtual keyboard'),
  @('wallet','Secure wallet / digital authentication'),
  @('cubes','Blockchain hash verification'),
  @('robot','AI assistant support')
)
for ($i=0; $i -lt 8; $i++) {
  $col = $i % 4
  $row = [Math]::Floor($i / 4)
  $x = $fx0 + $col * $fw
  $y = $fy0 + $row * $fh
  Draw-Feature $g $x $y $fw $fh $features[$i][0] $features[$i][1]
}
$lineP = [System.Drawing.Pen]::new((C 90 0 120 255), 1.5)
for ($i=1; $i -lt 4; $i++) { $g.DrawLine($lineP, $fx0+$i*$fw, $fy0, $fx0+$i*$fw, $fy0+$fh*2) }
$g.DrawLine($lineP, $fx0, $fy0+$fh, $fx0+$fw*4, $fy0+$fh)
$lineP.Dispose()

Draw-Panel $g 785 1915 787 320 'CONCLUSION' '6' $true
$checks = @(
  'Enhances patient privacy and control',
  'Improves trust in medical records',
  'Supports secure digital healthcare transformation',
  'Reduces unauthorized access and tampering risks'
)
for ($i=0; $i -lt 4; $i++) {
  Draw-CircleIcon $g 'shield' 850 (1992 + $i*58) 38
  Draw-Text $g $checks[$i] 885 (1974 + $i*58) 455 52 20 ([System.Drawing.FontStyle]::Bold) (C 255 255 255 255)
}
Draw-CircleIcon $g 'shield' 1400 2072 210

# Technology foundation.
Draw-Panel $g 28 2252 1544 115 '' ''
Draw-Ribbon $g 520 2223 560 54 'TECHNOLOGY FOUNDATION' 29 ''
$sep = [System.Drawing.Pen]::new((C 115 0 130 255), 2)
foreach ($x in @(275, 540, 825, 1160)) { $g.DrawLine($sep, $x, 2280, $x, 2350) }
$sep.Dispose()
Draw-TechItem $g 55 220 'F' "Flask`nBackend"
Draw-TechItem $g 310 220 'SQL' "MySQL`nDatabase"
Draw-TechItem $g 585 250 'cubes' "Blockchain`nIntegrity Layer"
Draw-TechItem $g 900 320 'M' "Blockchain Authentication:`nGanache & MetaMask"
Draw-TechItem $g 1240 290 'AI' "Meta AI / LLaMA`nAI Assistant"

$bmp.Save($OutPath, [System.Drawing.Imaging.ImageFormat]::Png)
$g.Dispose()
$bmp.Dispose()
Write-Output $OutPath
