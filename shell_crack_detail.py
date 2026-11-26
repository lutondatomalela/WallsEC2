"""EC2 crack-law components and explicit layer geometry for shell studies.

The directional crack spacing and strain laws do not supply a coupled
mean relative strain. The final multiplication requires this independent
input; this module cannot produce a design verdict.
"""
from dataclasses import dataclass
from math import cos, isfinite, pi, sin

from wall_shell_service import BarLayer


@dataclass(frozen=True)
class OrthogonalFace:
    """One bonded family per axis. Cover is to the outer bar surface."""
    outer_axis: int
    cover_mm: float
    phi_x_mm: float
    phi_y_mm: float
    spacing_x_mm: float
    spacing_y_mm: float
    layer_gap_mm: float = 0.

    def layers(self, h_mm, face):
        values = (h_mm, self.cover_mm, self.phi_x_mm, self.phi_y_mm,
                  self.spacing_x_mm, self.spacing_y_mm, self.layer_gap_mm)
        if (not all(map(isfinite, values)) or not all(v > 0 for v in values[:6])
                or self.layer_gap_mm < 0 or self.outer_axis not in (0, 1)
                or face not in (-1, 1)):
            raise ValueError("Geometria de armadura inválida")
        phi = (self.phi_x_mm, self.phi_y_mm)
        spacing = (self.spacing_x_mm, self.spacing_y_mm)
        inner_depth = self.cover_mm + phi[self.outer_axis] + self.layer_gap_mm
        out = []
        for i in (0, 1):
            cover = self.cover_mm if i == self.outer_axis else inner_depth
            if cover + phi[i] > h_mm/2:
                raise ValueError("Armadura excede a meia espessura atribuída à face")
            out.append(BarLayer(i, face*(h_mm/2-cover-phi[i]/2),
                                1000*pi*phi[i]**2/(4*spacing[i])))
        return tuple(out)


def relative_mean_strain(sigma_s, es, ec, rho_eff, fct_eff, kt=.4):
    """EC2 (7.9), bonded non-prestressed reinforcement in tension."""
    if (not all(map(isfinite, (sigma_s, es, ec, rho_eff, fct_eff, kt)))
            or sigma_s < 0 or min(es, ec, fct_eff) <= 0
            or not 0 < rho_eff < 1 or not 0 < kt <= 1):
        raise ValueError("Parâmetros de extensão relativa inválidos")
    return max((sigma_s-kt*fct_eff*(1/rho_eff+es/ec))/es, .6*sigma_s/es)


def crack_spacing_orthogonal(sr_x, sr_y, theta_rad):
    """EC2 (7.15); theta to direction X, folded into the first quadrant."""
    if (not all(map(isfinite, (sr_x, sr_y, theta_rad)))
            or min(sr_x, sr_y) <= 0 or not 0 <= theta_rad <= pi/2):
        raise ValueError("Espaçamento ou ângulo inválido")
    if theta_rad <= pi/12:
        return sr_x
    if theta_rad >= 5*pi/12:
        return sr_y
    return 1/(cos(theta_rad)/sr_x + sin(theta_rad)/sr_y)


@dataclass(frozen=True)
class TensionBand:
    """Geometric screen, not a validated shell effective concrete area."""
    face_strain: float
    opposite_strain: float
    tension_depth_mm: float
    candidate_depth_mm: float
    contains_bar_axis: bool


def projected_tension_band(h_mm, mid_strain, curvature, face, theta_rad, bar_depth_mm):
    """Project the strain tensor on an externally specified crack normal.

    Strain triples contain tensor shear (epsilon_xy, not gamma_xy).
    A wholly tensile section uses its half-thickness per face instead of
    the neutral-axis term. Band depth is a geometric extrapolation only.
    """
    if (len(mid_strain) != 3 or len(curvature) != 3
            or not all(map(isfinite, (h_mm, theta_rad, bar_depth_mm, *mid_strain, *curvature)))
            or face not in (-1, 1) or not 0 < bar_depth_mm < h_mm/2):
        raise ValueError("Dados inválidos para a banda de tracção")
    c, s = cos(theta_rad), sin(theta_rad)

    def project(tensor):
        x, y, xy = tensor
        return c*c*x + s*s*y + 2*c*s*xy

    mid = project(mid_strain)
    delta = face*h_mm/2*project(curvature)
    near, far = mid+delta, mid-delta
    if near <= 0:
        return TensionBand(near, far, 0., 0., False)
    if far < 0:
        tension = h_mm * (near/(near-far))
        neutral_limit = tension/3
    else:
        tension = h_mm
        neutral_limit = h_mm/2
    candidate = min(2.5*bar_depth_mm, neutral_limit, h_mm/2)
    return TensionBand(near, far, tension, candidate, bar_depth_mm <= candidate)


@dataclass(frozen=True)
class CrackJump:
    opening_mm: float
    slip_mm: float
    tangential_residual_strain: float


def recover_crack_jump(relative_strain, theta_rad, normal_spacing_mm,
                       strain_tolerance=1e-8):
    """Recover a displacement jump for one straight family of parallel cracks.

    relative_strain is the independently determined crack-induced strain
    tensor (xx, yy, xy), with continuous matrix strain already removed.
    theta_rad describes an independently established crack normal, and
    spacing is measured along that normal. This is a kinematic identity,
    not a constitutive model or an EC2 characteristic width calculation.
    """
    if (len(relative_strain) != 3
            or not all(map(isfinite, (*relative_strain, theta_rad, normal_spacing_mm, strain_tolerance)))
            or normal_spacing_mm <= 0 or strain_tolerance < 0):
        raise ValueError("Dados inválidos para recuperar a abertura")
    x, y, xy = relative_strain
    c, s = cos(theta_rad), sin(theta_rad)
    nn = c*c*x + s*s*y + 2*c*s*xy
    tt = s*s*x + c*c*y - 2*c*s*xy
    nt = c*s*(y-x) + (c*c-s*s)*xy
    if abs(tt) > strain_tolerance:
        raise ValueError("Extensões incompatíveis com uma única família de fendas")
    if nn < -strain_tolerance:
        raise ValueError("Salto normal negativo: fenda fechada ou dados incompatíveis")
    return CrackJump(max(nn, 0.)*normal_spacing_mm, 2*nt*normal_spacing_mm, tt)


def principal_relative_strain(delta_x, delta_y, gamma_xy):
    """Tan et al. (2019), Eq. (31), approximate membrane crack-normal strain.

    The inputs must represent independently determined mean relative normal
    strains and the engineering shear strain (not tensor shear). Neglects
    concrete shear strain, as in that expression. This function evaluates
    only the algebraic expression; it does not implement the MCMM bond-slip
    model or validate its extrapolation to bending/shear through a shell.
    DOI: 10.1016/j.engstruct.2019.109362.
    """
    from math import hypot
    if not all(map(isfinite, (delta_x, delta_y, gamma_xy))):
        raise ValueError('Extensões relativas inválidas')
    return max(0., (delta_x+delta_y)/2+hypot((delta_x-delta_y)/2,gamma_xy/2))
