from __future__ import division, print_function

import numpy as np

from canonical_system import CanonicalSystem
from obstacle import Obstacle
from repulsive import Ct, Ct_coupling
from attractive import Att

class PositionDMP():
    def __init__(self, n_bfs=10, alpha=48.0, beta=None, cs_alpha=None, cs=None):
        self.n_bfs = n_bfs
        self.alpha = alpha
        self.beta = beta if beta is not None else self.alpha / 4
        self.cs = cs if cs is not None else CanonicalSystem(alpha=cs_alpha if cs_alpha is not None else self.alpha/2)

        # Centres of the Gaussian basis functions
        self.c = np.exp(-self.cs.alpha * np.linspace(0, 1, self.n_bfs))

        # Variance of the Gaussian basis functions
        self.h = 1.0 / np.gradient(self.c)**2

        # Scaling factor
        self.Dp = np.identity(3)

        # Initially weights are zero (no forcing term)
        self.w = np.zeros((3, self.n_bfs))

        # Initial- and goal positions
        self.p0 = np.zeros(3)
        self.gp = np.zeros(3)

        self.reset()

    def step(self, x, dt, tau, x_target):
        def fp(xj):
            psi = np.exp(-self.h * (xj - self.c)**2)
            return self.Dp.dot(self.w.dot(psi) / psi.sum() * xj)

        # DMP system acceleration
        # TODO: Implement the transformation system differential equation for the acceleration, given that you know the
        # values of the following variables:
        # self.alpha, self.beta, self.gp, self.p, self.dp, tau, x
        #sphere  = Obstacle([0.575, 0.30, 0.45])
        #sphere = Obstacle([0., 0.25, 0.80])
        sphere  = Obstacle(self.demo_p[760])

       # x_target = self.p + (self.dp + self.alpha*( self.beta * (self.gp - self.p) - tau*self.dp ) / (tau * tau) * dt)*dt # target used for Att

        self.ddp = (self.alpha*( self.beta * (self.gp - self.p) - tau*self.dp ) + fp(x) + Ct_coupling(self.p, self.dp, sphere) + Att(x_target, self.p, sphere.pos) )/(tau*tau)

        # Integrate acceleration to obtain velocity
        self.dp += self.ddp * dt

        # Integrate velocity to obtain position
        self.p += self.dp * dt

        return self.p, self.dp, self.ddp

    def rollout(self, ts, tau):
        self.reset()

        if np.isscalar(tau):
            tau = np.full_like(ts, tau)

        x = self.cs.rollout(ts, tau)  # Integrate canonical system
        dt = np.gradient(ts) # Differential time vector

        n_steps = len(ts)
        p = np.empty((n_steps, 3))
        dp = np.empty((n_steps, 3))
        ddp = np.empty((n_steps, 3))

        for i in range(n_steps):
            p[i], dp[i], ddp[i] = self.step(x[i], dt[i], tau[i], self.demo_p[i]) # added target

        return p, dp, ddp

    def reset(self):
        self.p = self.p0.copy()
        self.dp = np.zeros(3)
        self.ddp = np.zeros(3)

    def fit_repulsion(self, positions, ts, tau):
        p = positions
        # Sanity-check input
        if len(p) != len(ts):
            raise RuntimeError("len(p) != len(ts)")
        

    def train(self, positions, ts, tau):
        self.demo_p = positions # added demo_p
        p = positions

        # Sanity-check input
        if len(p) != len(ts):
            raise RuntimeError("len(p) != len(ts)")

        # Initial- and goal positions
        self.p0 = p[0]
        self.gp = p[-1]

        # Differential time vector
        dt = np.gradient(ts)[:,np.newaxis]

        # Scaling factor
        self.Dp = np.diag(self.gp - self.p0)
        Dp_inv = np.linalg.inv(self.Dp)

        # Desired velocities and accelerations
        d_p = np.gradient(p, axis=0) / dt
        dd_p = np.gradient(d_p, axis=0) / dt

        # Integrate canonical system
        x = self.cs.rollout(ts, tau)

        # Set up system of equations to solve for weights
        def features(xj):
            psi = np.exp(-self.h * (xj - self.c)**2)
            return xj * psi / psi.sum()

        def forcing(j):
            return Dp_inv.dot(tau**2 * dd_p[j]
                - self.alpha * (self.beta * (self.gp - p[j]) - tau * d_p[j]))

        A = np.stack(features(xj) for xj in x)
        f = np.stack(forcing(j) for j in range(len(ts)))

        print(A.shape)
        print(f.shape)

        # Least squares solution for Aw = f (for each column of f)
        self.w = np.linalg.lstsq(A, f, rcond=None)[0].T

        # Cache variables for later inspection
        self.train_p = p
        self.train_d_p = d_p
        self.train_dd_p = dd_p
